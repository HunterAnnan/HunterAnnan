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
    fig, ax = plt.subplots(figsize=(16, 6))
    colors = plt.get_cmap('tab10').colors

    # Category Duration Graph
    def hours_formatter(x, pos):
        return f'{int(x)}h'

    for i, cat in enumerate(categories):
        ax.plot(date_range, cumulative_duration[cat], label=cat.replace('_', ' ').title(), color=colors[i % len(colors)], linewidth=2)
        
    ax.legend(loc='upper left')
    ax.set_ylabel('Cumulative Hours')
    ax.set_title('Hours split by Activity')
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(hours_formatter))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b'))

    fig.tight_layout()
    plt.savefig(output_path)
    plt.close()

def update_readme(readme_filepath, new_content: dict):
    print("Creating README.md with Garmin stats...")
    start_tag = "<!-- GARMIN_STATS:START -->"
    end_tag = "<!-- GARMIN_STATS:END -->"
    
    training_effect = new_content.get("training_effect", "")
    training_effect_str = f", focusing on {training_effect}" if training_effect and training_effect.upper() != "UNKNOWN" else ""

    if all(key in new_content for key in ["last_activity_type", "last_activity_location", "last_activity_date"]):
        moving_duration = new_content.get("moving_duration")
        if moving_duration is not None:
            total_minutes = round(moving_duration / 60)
            hours = total_minutes // 60
            minutes = total_minutes % 60
            if hours == 0:
                duration_str = f"{minutes}m"
            else:
                duration_str = f"{hours}h {minutes}m"
        else:
            duration_str = ""

        average_hr_val = new_content.get("average_hr")
        average_hr_str = str(int(round(average_hr_val))) if average_hr_val is not None else ""

        line1 = f"I last went {new_content['last_activity_type'].replace('_', ' ')} {new_content['last_activity_date']} in {new_content['last_activity_location']}."
        line2 = f"I was active for {duration_str}{training_effect_str}, and had an average heart rate of {average_hr_str}."
        content_last_activity = f"## My latest Garmin activity\n{line1}\n{line2}"
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
        all_types = ['cycling' if a['activityType']['typeKey'] == 'road_biking' else a['activityType']['typeKey'] for a in activities]
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
            if act_type == 'road_biking':
                act_type = 'cycling'
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
            "AEROBIC_BASE": "aerobic base training",
            "TEMPO": "tempo training",
            "LACTATE_THRESHOLD": "threshold power",
            "VO2MAX": "VO2 max",
            "ANAEROBIC_CAPACITY": "improving anaerobic capacity",
            "SPRINT": "sprints",
        }
        
        label = last_activity.get("trainingEffectLabel", "")
        training_effect = TRAINING_EFFECT_MAP.get(label, label.replace("_", " ").title())

        new_content = {
            "last_activity_type": last_activity["activityType"]["typeKey"],
            "last_activity_location": last_activity["locationName"],
            "last_activity_date": last_activity_date,
            "training_effect": training_effect,
            "moving_duration": last_activity.get("movingDuration"),
            "average_hr": last_activity.get("averageHR"),
        }

        update_readme(readme, new_content)
