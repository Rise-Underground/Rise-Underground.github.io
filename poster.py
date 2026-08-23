"""
X (Twitter) posting orchestrator for the Leaders of the Leaderboards
competition.

Meant to run hourly via GitHub Actions (same pattern as orchestrate.py).
Each run:
  1. Figures out what competition phase "now" falls into.
  2. Checks whether there's a scheduled post for this phase/hour that
     hasn't already gone out this cycle (tracked in x_post_state.json).
  3. If so: builds the tweet text from templates.py + live standings
     data, optionally captures a screenshot, posts it, updates state.

Use --dry-run to print what WOULD be posted without actually posting or
writing state -- safe to run repeatedly while testing.

Requires environment variables (GitHub Actions repository secrets):
    X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET
"""

import argparse
import json
import os
from datetime import datetime, timezone, timedelta

import tweepy

from competition_window import compute_competition_window, get_second_sunday_window
import templates
import leaderboard_data
from screenshot import capture_standings_screenshot

STATE_PATH = "x_post_state.json"
LEADERBOARD_URL = "https://rise-underground.github.io/index.html"

# ---------------------------------------------------------------------
# Schedule (all times UTC)
# ---------------------------------------------------------------------
COUNTDOWN_HOUR = 16
UPDATE_HOURS = [14, 20]          # twice a day, days 1-6
FINAL_DAY_HOURS = [8, 11, 14, 17, 20]   # 5 posts on the final day
WINNERS_HOUR = 15                # day after competition ends
THANKYOU_HOUR = 15               # two days after competition ends


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"cycle_start_key": None, "posted_ids": [], "rotation_indexes": {}}


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def next_rotation_index(state, key, list_length):
    """Cycles through a template list without immediate repeats across runs."""
    idx = state["rotation_indexes"].get(key, -1)
    idx = (idx + 1) % list_length
    state["rotation_indexes"][key] = idx
    return idx


def get_client_v2():
    return tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )


def get_client_v1():
    auth = tweepy.OAuth1UserHandler(
        os.environ["X_API_KEY"],
        os.environ["X_API_SECRET"],
        os.environ["X_ACCESS_TOKEN"],
        os.environ["X_ACCESS_TOKEN_SECRET"],
    )
    return tweepy.API(auth)


import re

URL_PATTERN = re.compile(r'https?://\S+')
TCO_LENGTH = 23  # X auto-shortens every URL to exactly this many chars


def x_effective_length(text):
    """Estimates the length X will actually count toward the 280 limit --
    any URL substring counts as exactly 23 chars (t.co auto-shortening),
    regardless of its real length."""
    def replace_url(m):
        return "x" * TCO_LENGTH
    normalized = URL_PATTERN.sub(replace_url, text)
    return len(normalized)


def post_tweet(text, image_path=None, dry_run=False):
    effective_len = x_effective_length(text)
    if effective_len > 280:
        print(f"!! WARNING: tweet text is ~{effective_len} chars (accounting for URL shortening), over the 280 limit. Truncating for safety.")
        text = text[:277] + "..."

    if dry_run:
        print("=" * 60)
        print("[DRY RUN] Would post:" + (f" (with image: {image_path})" if image_path else ""))
        print("-" * 60)
        print(text)
        print("=" * 60)
        return True

    media_ids = None
    if image_path and os.path.exists(image_path):
        api_v1 = get_client_v1()
        media = api_v1.media_upload(image_path)
        media_ids = [media.media_id]

    client = get_client_v2()
    client.create_tweet(text=text, media_ids=media_ids)
    print("Posted successfully.")
    return True


def format_next_competition_date(now):
    """Computes the actual next competition start date (2nd Sunday rule),
    used for the Thank You template's {next_competition_date} -- dynamic,
    not the hardcoded '3rd Sunday' text from the original draft."""
    start, _ = compute_competition_window(now)
    return start.strftime("%A, %B %-d, %Y")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print what would post, don't actually post or save state")
    parser.add_argument("--now", help="Override current time (ISO format, UTC) for testing, e.g. 2026-09-06T16:00:00")
    args = parser.parse_args()

    now = datetime.fromisoformat(args.now).replace(tzinfo=timezone.utc) if args.now else datetime.now(timezone.utc)

    # compute_competition_window() rolls forward to the NEXT window once
    # "now" is past the current one's end -- great for a countdown clock,
    # wrong for winners/thank-you math, which needs the window that JUST
    # ended. So: use the raw (non-rolling) current-month window for that,
    # and only fall back to compute_competition_window's rolled-forward
    # result for the countdown/live-competition phases below.
    most_recent_start, most_recent_end = get_second_sunday_window(now.year, now.month)
    if now < most_recent_start:
        # haven't reached this month's window yet -- the "most recent"
        # completed one is last month's
        prev_month = now.month - 1 or 12
        prev_year = now.year if now.month > 1 else now.year - 1
        most_recent_start, most_recent_end = get_second_sunday_window(prev_year, prev_month)

    start, end = compute_competition_window(now)
    one_week_before = start - timedelta(days=7)

    print(f"Now: {now.isoformat()}")
    print(f"Competition window (current/next): {start.isoformat()} -> {end.isoformat()}")
    print(f"Most recently completed/active window: {most_recent_start.isoformat()} -> {most_recent_end.isoformat()}")

    state = load_state()
    cycle_key = start.isoformat()
    if state.get("cycle_start_key") != cycle_key:
        print("New competition cycle detected -- resetting post state.")
        state = {"cycle_start_key": cycle_key, "posted_ids": [], "rotation_indexes": {}}

    final_day_date = end.date()
    winners_date = most_recent_end.date() + timedelta(days=1)
    thankyou_date = most_recent_end.date() + timedelta(days=2)

    post_id = None
    text = None
    image_path = None

    # ---------------- Countdown phase ----------------
    if one_week_before <= now < start:
        days_remaining = (start.date() - now.date()).days
        if days_remaining in templates.COUNTDOWN and now.hour == COUNTDOWN_HOUR:
            post_id = f"countdown_day{days_remaining}"
            if post_id not in state["posted_ids"]:
                text = templates.COUNTDOWN[days_remaining]

    # ---------------- Competition opens (once, right at start) ----------------
    elif now >= start and now < start + timedelta(hours=1) and "competition_opens" not in state["posted_ids"]:
        post_id = "competition_opens"
        text = templates.COMPETITION_OPENS.format(leaderboard_url=LEADERBOARD_URL)

    # ---------------- Live update days (1-6) ----------------
    elif start <= now < datetime.combine(final_day_date, datetime.min.time(), tzinfo=timezone.utc):
        if now.hour in UPDATE_HOURS:
            slot_index = UPDATE_HOURS.index(now.hour)
            post_id = f"update_{now.date().isoformat()}_{slot_index}"
            if post_id not in state["posted_ids"]:
                standings = leaderboard_data.load_standings()
                days_remaining = (end.date() - now.date()).days
                data = leaderboard_data.top_n(standings, 3)
                data["days_remaining"] = days_remaining
                data["leaderboard_url"] = LEADERBOARD_URL
                idx = next_rotation_index(state, "leaderboard_update", len(templates.LEADERBOARD_UPDATES))
                text = templates.LEADERBOARD_UPDATES[idx].format(**data)

    # ---------------- Final day (5 posts, boilerplate or movement) ----------------
    elif now.date() == final_day_date and now <= end:
        if now.hour in FINAL_DAY_HOURS:
            slot_index = FINAL_DAY_HOURS.index(now.hour)
            post_id = f"finalday_{slot_index}"
            if post_id not in state["posted_ids"]:
                standings = leaderboard_data.load_standings()
                prev_snapshot = leaderboard_data.load_snapshot()
                movement = leaderboard_data.detect_movement(prev_snapshot, standings)

                days_remaining = max((end.date() - now.date()).days, 0)
                data = leaderboard_data.top_n(standings, 3)
                data["days_remaining"] = days_remaining
                data["leaderboard_url"] = LEADERBOARD_URL

                if movement is None:
                    idx = next_rotation_index(state, "finalday_boilerplate", len(templates.FINAL_DAY_BOILERPLATE))
                    text = templates.FINAL_DAY_BOILERPLATE[idx].format(**data)
                elif movement["type"] == "entered_top3":
                    idx = next_rotation_index(state, "finalday_entered_top3", len(templates.FINAL_DAY_ENTERED_TOP3))
                    data.update(movement)
                    text = templates.FINAL_DAY_ENTERED_TOP3[idx].format(**data)
                else:  # moved_up
                    idx = next_rotation_index(state, "finalday_moved_up", len(templates.FINAL_DAY_MOVED_UP))
                    data.update(movement)
                    text = templates.FINAL_DAY_MOVED_UP[idx].format(**data)

                if not args.dry_run:
                    leaderboard_data.save_snapshot(standings)
                image_path = "leaderboard_screenshot.png"
                if not capture_standings_screenshot(image_path):
                    image_path = None

    # ---------------- Winners announcement (day after end) ----------------
    elif now.date() == winners_date and now.hour == WINNERS_HOUR and "winners" not in state["posted_ids"]:
        post_id = "winners"
        standings = leaderboard_data.load_standings()
        if len(standings) >= 1:
            data = {
                "winner_name": standings[0]["name"],
                "winner_points": standings[0]["points"],
                "top2_name": standings[1]["name"] if len(standings) > 1 else "—",
                "top3_name": standings[2]["name"] if len(standings) > 2 else "—",
            }
            idx = next_rotation_index(state, "winners", len(templates.WINNERS_ANNOUNCEMENT))
            text = templates.WINNERS_ANNOUNCEMENT[idx].format(**data)
            image_path = "leaderboard_screenshot.png"
            if not capture_standings_screenshot(image_path):
                image_path = None
        else:
            print("No standings data available -- skipping winners announcement.")

    # ---------------- Thank you / next competition (2 days after end) ----------------
    elif now.date() == thankyou_date and now.hour == THANKYOU_HOUR and "thankyou" not in state["posted_ids"]:
        post_id = "thankyou"
        next_date_str = format_next_competition_date(now)
        idx = next_rotation_index(state, "thankyou", len(templates.THANK_YOU))
        text = templates.THANK_YOU[idx].format(next_competition_date=next_date_str)

    # ---------------- Nothing scheduled this run ----------------
    if text is None:
        print("Nothing scheduled to post this run.")
        if not args.dry_run:
            save_state(state)
        return

    print(f"Post ID: {post_id}")
    post_tweet(text, image_path=image_path, dry_run=args.dry_run)

    if not args.dry_run:
        state["posted_ids"].append(post_id)
        save_state(state)


if __name__ == "__main__":
    main()
