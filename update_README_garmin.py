from garminconnect import Garmin
from datetime import date, timedelta
from temp_credentials import email, password
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import itertools
import os

class GarminConnector():
    def __init__(self):
        self.client = self.connect()

    def connect(self):
        print("Connecting to Garmin...")
        
        # email = os.getenv("GARMIN_EMAIL")
        # password = os.getenv("GARMIN_PASSWORD")
        
        try:
            client = Garmin(email, password)
            client.login()
            return client
        except Exception as e:
            print(f"Login failed: {e}")
            return None
        
    def get_yearly_stats(self):
        if not self.client:
            print("Cannot fetch stats because login failed.")
            return None
        
        print("Fetching yearly stats from Garmin...")
        today = date.today()
        start_of_year = date(today.year, 1, 1)
        
        try:
            # Fetch all daily stats from the start of the year until today
            all_stats = self.client.get_daily_steps(start_of_year.isoformat(), today.isoformat())
            return all_stats
        except Exception as e:
            print(f"Failed to fetch stats: {e}")
            return None

def generate_graph(stats, output_path):
    print(f"Generating graph at {output_path}...")
    dates = [date.fromisoformat(s['calendarDate']) for s in stats if s]
    steps = [s.get('totalSteps', 0) for s in stats if s]
    cumulative_steps = list(itertools.accumulate(steps))

    plt.xkcd()
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(dates, cumulative_steps)

    # Format the y-axis to show millions with an "M" suffix
    def millions_formatter(x, pos):
        return f'{x*1e-6:.1f}M'
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(millions_formatter))

    # Format the x-axis to show abbreviated month names
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b'))

    # Set axis labels and title
    ax.set_ylabel('Steps')
    ax.set_title(f'Cumulative Steps for {date.today().year}')

    fig.tight_layout()
    plt.savefig(output_path)
    print("Graph saved successfully!")

def update_readme(readme_filepath, new_content: dict):
    print("Creating README.md with Garmin stats...")
    start_tag = "<!-- GARMIN_STATS:START -->"
    end_tag = "<!-- GARMIN_STATS:END -->"
    
    training_effect = new_content.get("training_effect", "")
    training_effect_str = f", focusing on {training_effect}" if training_effect else ""

    # if last_activity_type, last_activity_location, and last_activity_date are in new_content:
    if all(key in new_content for key in ["last_activity_type", "last_activity_location", "last_activity_date"]):
        content_last_activity = f"## Latest updates from Garmin\n" \
            f"I last went {new_content['last_activity_type']} {new_content['last_activity_date']}, in {new_content['last_activity_location']}{training_effect_str}."
    else:
        content_last_activity = ""
        
    with open(readme_filepath, "r", encoding="utf-8") as f:
        readme_content = f.read()
        
    try:
        before_stats, rest = readme_content.split(start_tag)
        _, after_stats = rest.split(end_tag)

        updated_readme = f"{before_stats}{start_tag}\n{content_last_activity}\n{end_tag}{after_stats}"
    except ValueError:
        print("Error: Could not find the Garmin comment tags in your README.md.")
        return
    
    with open(readme_filepath, "w", encoding="utf-8") as f:
        f.write(updated_readme)
        
    print("README updated successfully!")
        
if __name__ == "__main__":
    readme = "README.md"

    garmin_connection = GarminConnector()
    # stats = garmin_connection.get_yearly_stats()

    # if stats:
    #     generate_graph(stats, graph_path)
    
    today = date.today()
    yesterday = (date.today() - timedelta(days=1))
    start_of_last_week = (date.today() - timedelta(days=7))
    
    last_activity = garmin_connection.client.get_last_activity()
    
    # test = garmin_connection.client.get_activities(start=20)
    # import json
    # with open("garmin_activities.json", "w", encoding="utf-8") as f:
    #     json.dump(test, f, indent=4)
    

    # Activity date
    last_activity_date_raw = last_activity["startTimeLocal"].split(" ")[0]
    last_activity_date = date.fromisoformat(last_activity_date_raw).strftime("%-d %B %Y")
    if last_activity_date == today.strftime("%-d %B %Y"):
        last_activity_date = "today"
    elif last_activity_date == yesterday.strftime("%-d %B %Y"):
        last_activity_date = "yesterday"
    else:
        last_activity_date = "on " + last_activity_date

    TRAINING_EFFECT_MAP = {
        "RECOVERY": "recovery",
        "VO2MAX": "VO2 Max",
        "ANAEROBIC_CAPACITY": "anaerobic capacity",
        "BASE": "base training",
        "TEMPO": "tempo",
        "THRESHOLD": "threshold",
        "SPRINT": "sprint",
    }
    
    label = last_activity.get("trainingEffectLabel", "")
    training_effect = TRAINING_EFFECT_MAP.get(label, label.replace("_", " ").title())

    new_content = {
        "last_activity_type": last_activity["activityType"]["typeKey"],
        "last_activity_location": last_activity["locationName"],
        "last_activity_date": last_activity_date,
        "training_effect": training_effect,
    }

    update_readme(readme, new_content)
    

    