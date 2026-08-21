"""
Infinity Rising — Competition Orchestrator
=============================================

Meant to be run on a schedule (every hour, via GitHub Actions). Each
run decides what to do based on where "now" falls relative to the
current/next competition window:

  - Before the competition starts: do nothing.
  - Right at/after start (first run since start): run discover_catalog.py
    once.
  - Every hour after start, until the competition ends: run
    fast_scraper.py.
  - After the competition ends: do nothing — the last scrape's data
    stays as-is until the next competition's start triggers a fresh
    catalog discovery + scrape cycle.

State (what's already been done for the current competition window) is
tracked in competition_state.json, which must be committed back to the
repo after each run so it persists across separate scheduled runs.
"""

import json
import os
import subprocess
from datetime import datetime, timezone
from competition_window import compute_competition_window

STATE_PATH = "competition_state.json"
LOG_PATH = "orchestrator_run_log.csv"
SCRAPE_INTERVAL_SECONDS = 1 * 3600


def log_run(action, detail=""):
    """Appends one row to orchestrator_run_log.csv -- called at every
    decision point in main(), whether or not anything actually ran, so
    there's a record of *why* nothing happened as well as when something
    did. This file gets committed back to the repo by the workflow's
    existing 'git add -A' step, same as competition_state.json."""
    is_new = not os.path.exists(LOG_PATH)
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        if is_new:
            f.write("timestamp_utc,action,detail\n")
        timestamp = datetime.now(timezone.utc).isoformat()
        safe_detail = str(detail).replace('"', "'").replace("\n", " ")
        f.write(f'{timestamp},{action},"{safe_detail}"\n')


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"catalog_done_for_start": None, "last_scrape_slot_for_start": None, "last_scrape_slot_index": -1}


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def run(cmd):
    print(f"--- Running: {cmd} ---")
    result = subprocess.run(cmd, shell=True)
    ok = result.returncode == 0
    print(f"--- {'OK' if ok else 'FAILED'} ---")
    return ok


def reset_leaderboard_csvs():
    """Wipes ir_leaderboard_placements.csv back to just its header the
    moment a new competition window is detected — so the site shows a
    cleared board immediately at start, instead of showing the previous
    period's scores until the first hourly scrape overwrites them."""
    print("New competition period — clearing leaderboard placements immediately...")
    with open("ir_leaderboard_placements.csv", "w", newline="", encoding="utf-8") as f:
        f.write("player,board,rank,points,raw_time\n")


def main():
    now = datetime.now(timezone.utc)
    start, end = compute_competition_window(now)
    print(f"Now:              {now.isoformat()}")
    print(f"Competition window: {start.isoformat()} -> {end.isoformat()}")

    if now < start:
        print(f"Competition hasn't started yet (starts in {start - now}). Nothing to do.")
        log_run("waiting_for_start", f"starts in {start - now}")
        return

    if now > end:
        print("Competition already ended. Data stays frozen until the next one starts. Nothing to do.")
        log_run("competition_ended", f"ended at {end.isoformat()}")
        return

    state = load_state()
    start_key = start.isoformat()

    # --- Catalog discovery: once, right at/after competition start ---
    if state.get("catalog_done_for_start") != start_key:
        print("New competition window detected — running catalog discovery...")
        reset_leaderboard_csvs()
        if run("python discover_catalog.py"):
            state["catalog_done_for_start"] = start_key
            state["last_scrape_slot_for_start"] = start_key
            state["last_scrape_slot_index"] = -1
            save_state(state)
            log_run("catalog_discovery_ran", f"for window starting {start_key}")
        else:
            print("!! discover_catalog.py failed — will retry on next scheduled run.")
            log_run("catalog_discovery_failed", f"for window starting {start_key} -- will retry next run")
            return

    # --- Fast scrape: every hour after start, until end ---
    elapsed_seconds = (now - start).total_seconds()
    if elapsed_seconds < SCRAPE_INTERVAL_SECONDS:
        print(f"Competition started {elapsed_seconds/3600:.1f}h ago — "
              f"waiting for the first hourly scrape window.")
        log_run("waiting_first_scrape", f"competition started {elapsed_seconds/3600:.1f}h ago")
        return

    if state.get("last_scrape_slot_for_start") != start_key:
        state["last_scrape_slot_for_start"] = start_key
        state["last_scrape_slot_index"] = -1

    target_slot = int(elapsed_seconds // SCRAPE_INTERVAL_SECONDS)
    if target_slot > state.get("last_scrape_slot_index", -1):
        print(f"New hourly slot reached (#{target_slot}) — running fast scrape...")
        if run("python fast_scraper.py"):
            state["last_scrape_slot_index"] = target_slot
            save_state(state)
            log_run("scrape_ran", f"slot #{target_slot}")
        else:
            print("!! fast_scraper.py failed — will retry on next scheduled run.")
            log_run("scrape_failed", f"slot #{target_slot} -- will retry next run")
    else:
        print(f"Already scraped for slot #{target_slot}. Nothing to do this run.")
        log_run("already_done_this_slot", f"slot #{target_slot}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Anything unexpected (e.g. compute_competition_window itself
        # raising) still gets a log line explaining why, before the
        # workflow shows its normal red X for a genuine crash.
        log_run("crashed", f"{e.__class__.__name__}: {e}")
        raise
