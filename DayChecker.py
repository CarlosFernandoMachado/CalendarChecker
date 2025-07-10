import datetime
import requests
from icalendar import Calendar

# --- Configuration ---

# The iCalendar URL you want to inspect.
ICAL_URL = "https://www.airbnb.com/calendar/ical/666023464844106651.ics?s=fa7af763106779964d64c48f6cfed447"


def get_booked_dates(url):
    """
    Fetches an iCal from a URL and returns a list of all dates that are booked.
    """
    booked_dates = set()
    try:
        response = requests.get(url)
        response.raise_for_status()
        cal = Calendar.from_ical(response.text)

        for component in cal.walk():
            if component.name == "VEVENT":
                summary = str(component.get('summary', '')).lower()

                if "not available" in summary or "reserved" in summary:
                    # --- Start of new debugging prints ---
                    print(f"\n[!] Matched event with summary: '{summary}'")
                    dtstart = component.get('dtstart').dt
                    dtend = component.get('dtend').dt
                    print(f"    > Raw start from iCal: {dtstart}")
                    print(f"    > Raw end from iCal:   {dtend}")
                    # --- End of new debugging prints ---

                    # Convert to date objects
                    start_date = dtstart.date() if isinstance(dtstart, datetime.datetime) else dtstart
                    end_date = dtend.date() if isinstance(dtend, datetime.datetime) else dtend

                    current_date = start_date
                    while current_date < end_date:
                        booked_dates.add(current_date)
                        current_date += datetime.timedelta(days=1)

    except requests.exceptions.RequestException as e:
        print(f"Error fetching iCal from {url}: {e}")
    except Exception as e:
        print(f"An error occurred while processing the calendar: {e}")

    return booked_dates


def main():
    """
    Checks the status of each day for July 2025 and prints it.
    """
    if "YOUR_ICAL_URL" in ICAL_URL:
        print("Please update the ICAL_URL variable with a valid iCalendar link.")
        return

    print(f"Fetching calendar data from URL...")
    booked_dates = get_booked_dates(ICAL_URL)

    if not booked_dates and "YOUR_ICAL_URL" not in ICAL_URL:
        print("Could not retrieve any booked dates. The calendar might be empty or an error occurred.")

    print(f"\n--- Daily Status for July 2025 ---")

    start_of_july = datetime.date(2025, 7, 1)
    # July has 31 days
    num_days_in_july = 31

    for i in range(num_days_in_july):
        current_day = start_of_july + datetime.timedelta(days=i)

        if current_day in booked_dates:
            # Print the status for the current day
            print(f"{current_day.strftime('%Y-%m-%d (%A)')}: booked")




if __name__ == '__main__':
    main()
