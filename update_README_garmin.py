"""Garmin Connect Integration for README.md.

Uses the garminconnect package to fetch activities, then:
  1. Updates a one-line "last activity" statement in README.md (type + date only,
     so it doesn't depend on optional fields that Garmin sometimes omits).
  2. Regenerates the cumulative hours-by-activity chart for the current year.

The two steps are independent: if the chart fails, the statement is still updated.
"""

from datetime import date, datetime, timedelta
import itertools
import os
import sys

from garminconnect import Garmin
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

try:
    from temp_credentials import email, password
except ImportError:
    email, password = "", ""

START_TAG = "<!-- GARMIN_STATS:START -->"
END_TAG = "<!-- GARMIN_STATS:END -->"

# Garmin typeKey -> chart category. Anything not listed keeps its own typeKey.
CATEGORY_MAP = {
    "road_biking": "cycling",
}

# typeKey -> phrase used in "I last {phrase} {day}."
ACTIVITY_PHRASES = {
    "running": "went for a run",
    "trail_running": "went for a trail run",
    "treadmill_running": "did a treadmill run",
    "walking": "went for a walk",
    "casual_walking": "went for a walk",
    "speed_walking": "went for a walk",
    "hiking": "went for a hike",
    "cycling": "went for a bike ride",
    "road_biking": "went for a bike ride",
    "mountain_biking": "went for a bike ride",
    "gravel_cycling": "went for a bike ride",
    "indoor_cycling": "did an indoor cycle",
    "lap_swimming": "went for a swim",
    "open_water_swimming": "went for a swim",
    "swimming": "went for a swim",
    "strength_training": "did a strength session",
    "yoga": "did a yoga session",
    "pilates": "did a pilates session",
}


def parse_start(activity):
    """Returns the local start datetime of an activity."""
    return datetime.strptime(activity["startTimeLocal"], "%Y-%m-%d %H:%M:%S")


def category_of(activity):
    """Returns the chart category for an activity."""
    key = (activity.get("activityType") or {}).get("typeKey") or "other"
    # Catches walking, casual_walking, speed_walking, hiking, etc.
    if "walking" in key or "hiking" in key:
        return "hiking_walking"
    # Catches cycling, indoor_cycling, road_biking, mountain_biking, etc.
    if "cycling" in key or "biking" in key:
        return "cycling"
    # Catches rowing and indoor_rowing.
    if "rowing" in key:
        return "rowing"
    return CATEGORY_MAP.get(key, key)


def connect():
    """Logs in to Garmin Connect; returns a client or None."""
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


def get_yearly_activities(client):
    """Fetches all activities since 1 January of the current year."""
    print("Fetching yearly activities from Garmin...")
    start_of_year = date(date.today().year, 1, 1)
    activities = []
    start, limit = 0, 100
    while True:
        batch = client.get_activities(start, limit)
        if not batch:
            break
        done = False
        for a in batch:
            if parse_start(a).date() >= start_of_year:
                activities.append(a)
            else:
                done = True
        if done:
            break
        start += limit
    return activities


def generate_graph(activities, output_path):
    """Generates the cumulative hours-by-activity chart."""
    print(f"Generating graph at {output_path}...")
    today = date.today()
    start_of_year = date(today.year, 1, 1)
    days = (today - start_of_year).days + 1
    date_range = [start_of_year + timedelta(days=i) for i in range(days)]

    # Top 7 categories by count (+ "other" = 8 lines).
    counts = {}
    for a in activities:
        counts[category_of(a)] = counts.get(category_of(a), 0) + 1
    top = [c for c, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:7]]
    categories = top + ["other"]

    per_day = {cat: [0.0] * days for cat in categories}
    for a in activities:
        idx = (parse_start(a).date() - start_of_year).days
        if 0 <= idx < days:
            cat = category_of(a)
            cat = cat if cat in top else "other"
            per_day[cat][idx] += (a.get("duration") or 0) / 3600.0
    cumulative = {cat: list(itertools.accumulate(v)) for cat, v in per_day.items()}

    plt.xkcd()
    fig, ax = plt.subplots(figsize=(16, 6))
    colors = plt.get_cmap("tab10").colors
    for i, cat in enumerate(categories):
        label = "Hiking/Walking" if cat == "hiking_walking" else cat.replace("_", " ").title()
        ax.plot(date_range, cumulative[cat], label=label, color=colors[i % len(colors)], linewidth=2)
    ax.legend(loc="upper left")
    ax.set_ylabel("Cumulative Hours")
    ax.set_title("Hours split by Activity")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, pos: f"{int(x)}h"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    fig.tight_layout()
    plt.savefig(output_path)
    plt.close()


def describe_last_activity(activity):
    """Builds e.g. 'I last went for a run yesterday.'"""
    key = (activity.get("activityType") or {}).get("typeKey") or ""
    phrase = ACTIVITY_PHRASES.get(key)
    if not phrase:
        # Unmapped type: still reads fine, e.g. "did some rowing".
        phrase = f"did some {key.replace('_', ' ')}" if key else "did an activity"

    when = parse_start(activity).date()
    today = date.today()
    if when == today:
        when_str = "today"
    elif when == today - timedelta(days=1):
        when_str = "yesterday"
    else:
        when_str = f"on {when.day} {when.strftime('%B %Y')}"
    return f"I last {phrase} {when_str}."


def update_readme(readme_path, statement):
    """Replaces the content between the tags in README.md."""
    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()
    try:
        before, rest = content.split(START_TAG)
        _, after = rest.split(END_TAG)
    except ValueError:
        print("Error: Garmin comment tags not found in README.md.")
        return False
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(f"{before}{START_TAG}\n{statement}\n{END_TAG}{after}")
    print("README updated.")
    return True


def main():
    """Fetches data, updates the statement, then the chart."""
    client = connect()
    if not client:
        sys.exit(1)

    # Step 1: last-activity statement (needs only the newest activity).
    try:
        recent = client.get_activities(0, 5)
        if not recent:
            raise RuntimeError("No activities returned")
        last = max(recent, key=parse_start)
        update_readme("README.md", describe_last_activity(last))
    except Exception as e:
        print(f"Failed to update last-activity statement: {e}")
        sys.exit(1)

    # Step 2: chart. Failure here is logged but doesn't fail the run.
    try:
        generate_graph(get_yearly_activities(client), "garmin_stats.png")
    except Exception as e:
        print(f"Warning: failed to update chart: {e}")


if __name__ == "__main__":
    main()
