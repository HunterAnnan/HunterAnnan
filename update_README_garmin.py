"""Garmin Connect Integration for README.md.

This script uses the garminconnect package to retrieve activity data from Garmin.
It then updates the repository's README.md with the latest activity details,
including dynamic duration-tracking and heart rate zone visualizations.
"""

from collections import Counter
from datetime import date, datetime, timedelta
import itertools
import os

from garminconnect import Garmin
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from temp_credentials import email, password


class GarminConnector:
    """Manages connection and interaction with Garmin Connect."""

    def __init__(self):
        """Initializes the connector and establishes a client connection."""
        self.client = self.connect()

    def connect(self):
        """Authenticates and connects to Garmin Connect using credentials."""
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
        """Fetches daily step stats from the start of the year."""
        if not self.client:
            print("Cannot fetch stats because login failed.")
            return None
        
        print("Fetching yearly stats from Garmin...")
        today = date.today()
        start_of_year = date(today.year, 1, 1)
        
        try:
            all_stats = self.client.get_daily_steps(start_of_year.isoformat(), today.isoformat())
            return all_stats
        except Exception as e:
            print(f"Failed to fetch stats: {e}")
            return None

    def get_yearly_activities(self):
        """Fetches all activities logged since the beginning of the current year."""
        if not self.client:
            return []
            
        print("Fetching yearly activities from Garmin...")
        activities = []
        start = 0
        limit = 100
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
            if start > 500:  # Safety break
                break
        return activities


def generate_combined_graph(date_range, count_per_day, categories, cumulative_duration, output_path):
    """Generates a combined cumulative activity duration chart and saves it as an image."""
    print(f"Generating combined graph at {output_path}...")
    plt.xkcd()
    fig, ax = plt.subplots(figsize=(16, 6))
    colors = plt.get_cmap('tab10').colors

    def hours_formatter(x, pos):
        return f'{int(x)}h'

    for i, cat in enumerate(categories):
        ax.plot(
            date_range, 
            cumulative_duration[cat], 
            label=cat.replace('_', ' ').title(), 
            color=colors[i % len(colors)], 
            linewidth=2
        )
        
    ax.legend(loc='upper left')
    ax.set_ylabel('Cumulative Hours')
    ax.set_title('Hours split by Activity')
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(hours_formatter))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b'))

    fig.tight_layout()
    plt.savefig(output_path)
    plt.close()


def generate_hr_zones_graph(last_activity, output_path):
    """Generates a horizontal stacked bar chart representing HR Zones 0-5.
    
    The bar heights scale with the zone level (Z0=0.15, Z5=1.1) and are bottom-aligned at y=0.
    """
    print(f"Generating HR zones graph at {output_path}...")
    
    raw_times_1_5 = [last_activity.get(f"hrTimeInZone_{i}", 0.0) or 0.0 for i in range(1, 6)]
    zones_1_5_time = sum(raw_times_1_5)
    total_duration = last_activity.get("duration", 0.0) or 0.0
    zone_0_time = max(0.0, total_duration - zones_1_5_time)
    
    all_times = [zone_0_time] + raw_times_1_5
    total_time = sum(all_times)
    
    if total_time > 0:
        percentages = [t / total_time * 100 for t in all_times]
    else:
        percentages = [0.0] * 6
        
    colors = ['#D3D3D3', '#9E9E9E', '#2196F3', '#4CAF50', '#FF9800', '#F44336']
    heights = [0.15, 0.3, 0.5, 0.7, 0.9, 1.1]
    
    plt.xkcd()
    fig, ax = plt.subplots(figsize=(16, 2.2))
    left = 0
    last_label_x = -999.0
    min_distance = 5.0  # Minimum percentage distance between labels to prevent overlapping
    
    for i, (pct, color, h) in enumerate(zip(percentages, colors, heights)):
        if pct > 0:
            ax.barh(h / 2, pct, left=left, height=h, color=color, edgecolor='black', linewidth=1.5)
            # Center of the current segment
            label_x = left + pct / 2
            # Suppress label if the segment is too small or overlaps with the previous label
            if pct >= 5.0 and (label_x - last_label_x) >= min_distance:
                # Add label below the bar (below y=0)
                ax.text(
                    label_x, 
                    -0.1, 
                    f"Zone {i}\n{pct:.1f}%", 
                    ha='center', 
                    va='top', 
                    color='black', 
                    fontsize=9, 
                    fontweight='bold'
                )
                last_label_x = label_x
            left += pct
            
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.6, 1.3)  # Leave space below y=0 for the labels
    ax.set_yticks([])
    ax.set_xticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
        
    fig.tight_layout()
    plt.savefig(output_path)
    plt.close()


def update_readme(readme_filepath, new_content: dict):
    """Updates the README.md file with the latest Garmin activity stats within tags."""
    print("Creating README.md with Garmin stats...")
    start_tag = "<!-- GARMIN_STATS:START -->"
    end_tag = "<!-- GARMIN_STATS:END -->"
    
    training_effect = new_content.get("training_effect", "")
    training_effect_str = (
        f", focusing on {training_effect}"
        if training_effect and training_effect.upper() != "UNKNOWN"
        else ""
    )

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

        line1 = (
            f"I last went {new_content['last_activity_type'].replace('_', ' ')} "
            f"{new_content['last_activity_date']} in {new_content['last_activity_location']}."
        )
        line2 = f"I was active for {duration_str}{training_effect_str}, and had an average heart rate of {average_hr_str}."
        
        show_hr_zones = new_content.get("show_hr_zones", True)
        hr_zones_str = "\n\n![Latest HR Zones](latest_hr_zones.png)" if show_hr_zones else ""
        content_last_activity = f"## Here what I last recorded on Garmin\n{line1}\n{line2}{hr_zones_str}"
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


def main():
    """Main execution function to fetch, process, plot, and update Garmin metrics."""
    readme = "README.md"
    stats_path = "garmin_stats.png"
    hr_zones_path = "latest_hr_zones.png"

    garmin_connection = GarminConnector()
    
    # Fetch all activities for the year
    activities = garmin_connection.get_yearly_activities()
    if activities:
        # Group activities by type and identify top 4
        all_types = [
            'cycling' if a['activityType']['typeKey'] == 'road_biking' else a['activityType']['typeKey']
            for a in activities
        ]
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
    yesterday = date.today() - timedelta(days=1)
    
    # Get the single last activity for the README text
    if activities:
        last_activity = activities[0]  # Activities are usually returned newest first
    elif garmin_connection.client:
        last_activity = garmin_connection.client.get_last_activity()
    else:
        last_activity = None
    
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

        zones_1_5_time = sum(last_activity.get(f"hrTimeInZone_{i}", 0.0) or 0.0 for i in range(1, 6))
        show_hr_zones = zones_1_5_time > 0

        new_content = {
            "last_activity_type": last_activity["activityType"]["typeKey"],
            "last_activity_location": last_activity["locationName"],
            "last_activity_date": last_activity_date,
            "training_effect": training_effect,
            "moving_duration": last_activity.get("movingDuration"),
            "average_hr": last_activity.get("averageHR"),
            "show_hr_zones": show_hr_zones,
        }

        if show_hr_zones:
            generate_hr_zones_graph(last_activity, hr_zones_path)
        else:
            if os.path.exists(hr_zones_path):
                try:
                    os.remove(hr_zones_path)
                except OSError:
                    pass
        update_readme(readme, new_content)


if __name__ == "__main__":
    main()
