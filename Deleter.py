import datetime
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these SCOPES, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar']

# --- Configuration ---

# ID of the Google Calendar to delete events from.
# Use 'primary' for your main default calendar.
TARGET_CALENDAR_ID = '23fa5720ef3cc607710e704104e2fe465cb4dae5a2b942d4ee000a0d60df88d0@group.calendar.google.com'

def get_google_calendar_service():
    """
    Authenticates with the Google Calendar API and returns a service object.
    """
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('calendar', 'v3', credentials=creds)

def main():
    """
    Finds and deletes events with "booked" in the summary for July 2025.
    """
    try:
        service = get_google_calendar_service()
        print("Successfully connected to Google Calendar API.")

        # Define the time range for July 2025
        time_min = datetime.datetime(2025, 7, 1).isoformat() + 'Z'  # Start of July 1st
        time_max = datetime.datetime(2026, 7, 1).isoformat() + 'Z'  # Start of August 1st

        print(f"\nSearching for events containing 'booked' in July 2025...")

        # Get all events matching the query within the time range
        events_result = service.events().list(
            calendarId=TARGET_CALENDAR_ID,
            q='booked',
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events_to_delete = events_result.get('items', [])

        if not events_to_delete:
            print("No events found to delete.")
            return

        print("\nThe following events will be deleted:")
        for event in events_to_delete:
            start = event['start'].get('dateTime', event['start'].get('date'))
            print(f"  - {event['summary']} on {start.split('T')[0]}")

        # Safety check: ask for user confirmation before deleting
        choice = 'yes'

        if choice == 'yes':
            print("\nDeleting events...")
            for event in events_to_delete:
                try:
                    service.events().delete(
                        calendarId=TARGET_CALENDAR_ID,
                        eventId=event['id']
                    ).execute()
                    start = event['start'].get('dateTime', event['start'].get('date'))
                    print(f"  > Deleted: {event['summary']} on {start.split('T')[0]}")
                except HttpError as e:
                    print(f"  > Failed to delete event '{event['summary']}': {e}")
            print("\nDeletion complete.")
        else:
            print("\nDeletion cancelled.")

    except HttpError as error:
        print(f'An error occurred with the Google Calendar API: {error}')
    except FileNotFoundError:
        print("Error: credentials.json not found. Please follow the setup instructions.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == '__main__':
    main()
