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
import math
import os
import sys
from datetime import datetime, timezone, timedelta

# Windows' console defaults to cp1252, which can't print emoji -- force
# UTF-8 so the tweet text (all the 🔥🏆🥇 etc.) doesn't crash on print,
# especially when output is redirected to a file (> results.txt).
sys.stdout.reconfigure(encoding="utf-8")

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
COUNTDOWN_TIME = (16, 0)
FINAL_COUNTDOWN_TIME = (22, 0)   # once, evening of the day before start (Sep 12)
UPDATE_TIMES = [(14, 0), (20, 0)]          # twice a day, days 1-6
FINAL_DAY_TIMES = [(8, 0), (11, 0), (14, 0), (17, 0), (20, 0)]   # 5 posts on the final day
WINNERS_TIME = (15, 0)                     # day after competition ends
MONDAY_WINNER_STATS_TIME = (15, 0)         # winner stats fanfare (rounded from 14:30)
MONDAY_CONTINUATION_TIME = (17, 0)         # monthly-continuation post (rounded from 16:30)


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
    # Note: "%-d" (no leading zero) is Linux/Mac-only and crashes on
    # Windows -- build the day number manually instead for portability.
    return f"{start.strftime('%A, %B')} {start.day}, {start.strftime('%Y')}"


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
    monday_date = most_recent_end.date() + timedelta(days=2)   # winner stats + continuation

    post_id = None
    text = None
    image_path = None

    now_hm = (now.hour, now.minute)

    # ---------------- Countdown phase ----------------
    if one_week_before <= now < start:
        days_remaining = (start.date() - now.date()).days

        if days_remaining in templates.COUNTDOWN and now_hm == COUNTDOWN_TIME:
            post_id = f"countdown_day{days_remaining}"
            if post_id not in state["posted_ids"]:
                text = templates.COUNTDOWN[days_remaining].format(leaderboard_url=LEADERBOARD_URL)

        elif days_remaining == 1 and now_hm == FINAL_COUNTDOWN_TIME:
            post_id = "final_countdown"
            if post_id not in state["posted_ids"]:
                diff_seconds = int((start - now).total_seconds())
                text = templates.FINAL_COUNTDOWN.format(
                    leaderboard_url=LEADERBOARD_URL,
                    hours_remaining=diff_seconds // 3600,
                    minutes_remaining=(diff_seconds % 3600) // 60,
                    seconds_remaining=diff_seconds % 60,
                )

    # ---------------- Competition opens (once, right at start) ----------------
    elif now >= start and now < start + timedelta(hours=1) and "competition_opens" not in state["posted_ids"]:
        post_id = "competition_opens"
        text = templates.COMPETITION_OPENS.format(leaderboard_url=LEADERBOARD_URL)

    # ---------------- Live update days (1-6) ----------------
    elif start <= now < datetime.combine(final_day_date, datetime.min.time(), tzinfo=timezone.utc):
        if now_hm in UPDATE_TIMES:
            slot_index = UPDATE_TIMES.index(now_hm)
            post_id = f"update_{now.date().isoformat()}_{slot_index}"
            if post_id not in state["posted_ids"]:
                standings = leaderboard_data.load_standings()
                days_remaining = (end.date() - now.date()).days
                data = leaderboard_data.top_n(standings, 3)
                data["days_remaining"] = days_remaining
                data["leaderboard_url"] = LEADERBOARD_URL
                idx = next_rotation_index(state, "leaderboard_update", len(templates.LEADERBOARD_UPDATES))
                text = templates.LEADERBOARD_UPDATES[idx].format(**data)
                image_path = "leaderboard_screenshot.png"
                if not capture_standings_screenshot(image_path):
                    image_path = None

    # ---------------- Final day (5 posts, boilerplate or movement) ----------------
    elif now.date() == final_day_date and now <= end:
        if now_hm in FINAL_DAY_TIMES:
            slot_index = FINAL_DAY_TIMES.index(now_hm)
            post_id = f"finalday_{slot_index}"
            if post_id not in state["posted_ids"]:
                standings = leaderboard_data.load_standings()
                prev_snapshot = leaderboard_data.load_snapshot()
                movement = leaderboard_data.detect_movement(prev_snapshot, standings)

                hours_remaining = max(1, math.ceil((end - now).total_seconds() / 3600))
                data = leaderboard_data.top_n(standings, 3)
                data["hours_remaining"] = hours_remaining
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
    elif now.date() == winners_date and now_hm == WINNERS_TIME and "winners" not in state["posted_ids"]:
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

    # ---------------- Monday: winner stats fanfare (14:30 UTC) ----------------
    elif now.date() == monday_date and now_hm == MONDAY_WINNER_STATS_TIME and "monday_winner_stats" not in state["posted_ids"]:
        post_id = "monday_winner_stats"
        standings = leaderboard_data.load_standings()
        if len(standings) >= 1:
            board_count = leaderboard_data.board_count_for_player(standings[0]["name"])
            data = {
                "winner_name": standings[0]["name"],
                "winner_points": standings[0]["points"],
                "winner_board_count": board_count,
            }
            text = templates.MONDAY_WINNER_STATS.format(**data)
            image_path = "leaderboard_screenshot.png"
            if not capture_standings_screenshot(image_path):
                image_path = None
        else:
            print("No standings data available -- skipping Monday winner stats post.")

    # ---------------- Monday: monthly continuation (16:30 UTC, no image) ----------------
    elif now.date() == monday_date and now_hm == MONDAY_CONTINUATION_TIME and "monday_continuation" not in state["posted_ids"]:
        post_id = "monday_continuation"
        next_date_str = format_next_competition_date(now)
        text = templates.MONDAY_CONTINUATION.format(next_competition_date=next_date_str)

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
