import datetime
import os
import json
import requests
from icalendar import Calendar
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load environment variables from .env file at the start
load_dotenv()

# If modifying these SCOPES, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar']

# --- Load Configuration from Environment Variables ---
TARGET_CALENDAR_ID = os.getenv('TARGET_CALENDAR_ID')
ICAL_CONFIG_JSON = os.getenv('ICAL_CONFIG_JSON')

# Validate that the environment variables are loaded correctly
if not TARGET_CALENDAR_ID or not ICAL_CONFIG_JSON:
    raise ValueError("Error: Environment variables TARGET_CALENDAR_ID and ICAL_CONFIG_JSON must be set.")

try:
    ICAL_CONFIG = json.loads(ICAL_CONFIG_JSON)
except json.JSONDecodeError:
    raise ValueError("Error: ICAL_CONFIG_JSON is not valid JSON.")


def get_google_calendar_service():
    """Authenticates with the Google Calendar API and returns a service object."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # This part should not run on a server. A valid token.json must exist.
            raise Exception("Error: token.json is missing or invalid. Please generate it locally first.")
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('calendar', 'v3', credentials=creds)


def merge_intervals(intervals):
    """Merges overlapping and adjacent date ranges."""
    if not intervals:
        return []
    intervals.sort(key=lambda x: x[0])
    merged = [intervals[0]]
    for current_start, current_end in intervals[1:]:
        last_start, last_end = merged[-1]
        if current_start <= last_end:
            merged[-1] = (last_start, max(last_end, current_end))
        else:
            merged.append((current_start, current_end))
    return merged


def sync_calendars():
    """
    Fetches events from iCal files, consolidates them, and performs a two-way sync
    (adds new events, deletes cancelled ones) with Google Calendar.
    """
    today = datetime.date.today()
    limit_date = today + datetime.timedelta(days=183)
    print(f"--- Starting Sync at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
    print(f"Processing bookings from today until {limit_date.strftime('%Y-%m-%d')}")

    # --- Phase 1: Data Collection ---
    booked_ranges_by_physical_room = {}
    print("\n--- Phase 1: Collecting all booking data from iCal files ---")
    for room_name, url in ICAL_CONFIG.items():
        print(f"  > Processing: {room_name}")
        try:
            response = requests.get(url)
            if response.status_code == 429:
                print(f"    [!] WARNING: Received 'Too Many Requests' (429) for {room_name}.")
                continue
            response.raise_for_status()

            cal = Calendar.from_ical(response.text)
            physical_room_name = room_name.split('.')[0]
            if physical_room_name not in booked_ranges_by_physical_room:
                booked_ranges_by_physical_room[physical_room_name] = []

            for component in cal.walk():
                if component.name == "VEVENT":
                    summary = str(component.get('summary', '')).lower()
                    if "not available" in summary or "reserved" in summary:
                        dtstart = component.get('dtstart').dt
                        dtend = component.get('dtend').dt
                        start_date = dtstart.date() if isinstance(dtstart, datetime.datetime) else dtstart
                        end_date = dtend.date() if isinstance(dtend, datetime.datetime) else dtend
                        booked_ranges_by_physical_room[physical_room_name].append((start_date, end_date))
        except Exception as e:
            print(f"    - Error processing {room_name}: {e}")

    # --- Phase 2: Syncing to Google Calendar ---
    print("\n--- Phase 2: Syncing consolidated bookings to Google Calendar ---")
    try:
        service = get_google_calendar_service()
        print("Successfully connected to Google Calendar API.")

        # 1. Get all events that SHOULD exist from iCal data
        should_exist_events = set()
        for physical_room, ranges in booked_ranges_by_physical_room.items():
            merged_bookings = merge_intervals(ranges)
            for start_date, end_date in merged_bookings:
                if end_date > today and start_date < limit_date:
                    summary = f"{physical_room} booked"
                    should_exist_events.add((summary, start_date, end_date))

        # 2. Get all events that CURRENTLY exist on Google Calendar
        print("  > Fetching existing events from Google Calendar...")
        existing_events_on_gcal = []
        time_min_utc = datetime.datetime.combine(today, datetime.time.min).isoformat() + 'Z'
        time_max_utc = datetime.datetime.combine(limit_date, datetime.time.max).isoformat() + 'Z'

        page_token = None
        while True:
            events_result = service.events().list(
                calendarId=TARGET_CALENDAR_ID, q='booked', timeMin=time_min_utc,
                timeMax=time_max_utc, singleEvents=True, pageToken=page_token
            ).execute()
            existing_events_on_gcal.extend(events_result.get('items', []))
            page_token = events_result.get('nextPageToken')
            if not page_token:
                break
        print(f"  > Found {len(existing_events_on_gcal)} existing 'booked' events in the target calendar.")

        # 3. Delete cancelled events (events on GCal that shouldn't exist)
        print("\n  > Checking for cancellations to delete...")
        events_to_delete = []
        existing_events_set_for_check = set()
        for event in existing_events_on_gcal:
            summary = event.get('summary')
            start_str = event.get('start', {}).get('date')
            end_str = event.get('end', {}).get('date')
            event_id = event.get('id')
            if summary and start_str and end_str and event_id:
                event_tuple = (summary, datetime.date.fromisoformat(start_str), datetime.date.fromisoformat(end_str))
                existing_events_set_for_check.add(event_tuple)
                if event_tuple not in should_exist_events:
                    events_to_delete.append(event)

        if not events_to_delete:
            print("  > No cancelled events found.")
        else:
            for event in events_to_delete:
                summary = event.get('summary')
                start_date = event.get('start', {}).get('date')
                print(f"  > Deleting cancelled event: '{summary}' on {start_date}")
                service.events().delete(calendarId=TARGET_CALENDAR_ID, eventId=event['id']).execute()

        # 4. Add new events (events that should exist but are not on GCal)
        print("\n  > Checking for new events to create...")
        new_events_created = 0
        for event_tuple in should_exist_events:
            if event_tuple not in existing_events_set_for_check:
                summary, start_date, end_date = event_tuple
                event_body = {
                    'summary': summary,
                    'start': {'date': start_date.isoformat()},
                    'end': {'date': end_date.isoformat()},
                    'description': f'Managed by iCal Merger Script for physical room: {summary.replace(" booked", "")}.'
                }
                service.events().insert(calendarId=TARGET_CALENDAR_ID, body=event_body).execute()
                print(f"  > Event created: '{summary}' from {start_date} to {end_date}")
                new_events_created += 1

        if new_events_created == 0:
            print("  > No new events to create.")

    except HttpError as error:
        print(f'An error occurred with the Google Calendar API: {error}')
    except FileNotFoundError:
        print("Error: credentials.json not found.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == '__main__':
    sync_calendars()
    print("\n--- Sync Complete ---")
