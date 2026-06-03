from garminconnect import Garmin
from datetime import date, timedelta, datetime
from temp_credentials import email, password
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import itertools
import os
from collections import Counter

class GarminConnector():
    def __init__(self):
        self.client = self.connect()

    def connect(self):
        print("Connecting to Garmin...")
        
        garmin_email = os.getenv("GARMIN_EMAIL") or email
        garmin_password = os.getenv("GARMIN_PASSWORD") or password
        
        try:
            client = Garmin(garmin_email, garmin_password)
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

    def get_yearly_activities(self):
        if not self.client:
            return []
        print("Fetching yearly activities from Garmin...")
        activities = []
        start = 0
        limit = 50
        today = date.today()
        start_of_year = date(today.year, 1, 1)
        
        while True:
            batch = self.client.get_activities(start, limit)
            if not batch:
                break
            
            for a in batch:
                a_date = datetime.strptime(a['startTimeLocal'], '%Y-%m-%d %H:%M:%S').date()
                if a_date >= start_of_year:
                    activities.append(a)
                else:
                    return activities
            
            start += limit
            if start > 500: # Safety break
                break
        return activities

def generate_combined_graph(date_range, count_per_day, categories, cumulative_duration, output_path):
    print(f"Generating combined graph at {output_path}...")
    plt.xkcd()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    colors = plt.get_cmap('tab10').colors

    # Graph 1: Total Count
    total_cumulative_count = list(itertools.accumulate(count_per_day))
    ax1.bar(date_range, total_cumulative_count, color='black')
    ax1.set_ylabel('Activities')
    ax1.set_title('Activities this Year')
    ax1.xaxis.set_major_locator(mdates.MonthLocator())
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%b'))

    # Graph 2: Category Duration
    def hours_formatter(x, pos):
        return f'{int(x)}h'

    for i, cat in enumerate(categories):
        ax2.plot(date_range, cumulative_duration[cat], label=cat.replace('_', ' ').title(), color=colors[i % len(colors)], linewidth=2)
        
    ax2.legend(loc='upper left')
    ax2.set_ylabel('Cumulative Hours')
    ax2.set_title('Hours split by Activity')
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(hours_formatter))
    ax2.xaxis.set_major_locator(mdates.MonthLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%b'))

    fig.tight_layout()
    plt.savefig(output_path)
    plt.close()

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
    stats_path = "garmin_stats.png"

    garmin_connection = GarminConnector()
    
    # Fetch all activities for the year
    activities = garmin_connection.get_yearly_activities()
    if activities:
        # Group activities by type and identify top 4
        all_types = [a['activityType']['typeKey'] for a in activities]
        counts = Counter(all_types)
        top_4_types = [t for t, c in counts.most_common(4)]
        
        today = date.today()
        start_of_year = date(today.year, 1, 1)
        date_range = [start_of_year + timedelta(days=i) for i in range((today - start_of_year).days + 1)]
        
        categories = top_4_types + ["Other"]
        duration_per_day = {cat: [0.0] * len(date_range) for cat in categories}
        count_per_day = [0] * len(date_range)
        
        for activity in activities:
            act_date = datetime.strptime(activity['startTimeLocal'], '%Y-%m-%d %H:%M:%S').date()
            if act_date < start_of_year:
                continue
            
            day_idx = (act_date - start_of_year).days
            if day_idx >= len(date_range):
                continue
                
            act_type = activity['activityType']['typeKey']
            cat = act_type if act_type in top_4_types else "Other"
            
            duration_per_day[cat][day_idx] += activity.get('duration', 0) / 3600.0
            count_per_day[day_idx] += 1
            
        cumulative_duration = {cat: list(itertools.accumulate(duration_per_day[cat])) for cat in categories}
        
        generate_combined_graph(date_range, count_per_day, categories, cumulative_duration, stats_path)
    
    today = date.today()
    yesterday = (date.today() - timedelta(days=1))
    
    # Get the single last activity for the README text
    if activities:
        last_activity = activities[0] # Activities are usually returned newest first
    else:
        last_activity = garmin_connection.client.get_last_activity()
    
    if last_activity:
        # Activity date
        last_activity_date_raw = last_activity["startTimeLocal"].split(" ")[0]
        last_activity_date_dt = datetime.strptime(last_activity_date_raw, "%Y-%m-%d").date()
        
        if last_activity_date_dt == today:
            last_activity_date = "today"
        elif last_activity_date_dt == yesterday:
            last_activity_date = "yesterday"
        else:
            last_activity_date = "on " + last_activity_date_dt.strftime("%-d %B %Y")

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
