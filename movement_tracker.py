"""
movement_tracker.py -- persistent hourly leaderboard movement log.

Called by orchestrate.py right after each successful fast_scraper.py run.
Each call:
  1. Reads the freshly-scraped ir_leaderboard_placements.csv.
  2. Compares it to the most recent prior snapshot in this competition's
     log file, detecting:
       - "board_takeover": a board's #1 spot changed hands.
       - "aggregate_move": a player's overall rank moved significantly
         (up or down) in the summed-points standings.
  3. Appends this hour's snapshot + any detected movements to the log.

One log file per competition, named by the competition's start month
(lotlb_2026_09.json, lotlb_2026_10.json, ...) so each month's history
stays separate and nothing needs manual resetting -- a new month's
competition automatically starts a fresh file.

This file is meant to be fetched later (e.g. by the X Post Expediter
tool) to build "recap the last N hours" style posts, and is otherwise
just a durable historical record -- also handy later for other graphics
built from the same data, not just single-post recaps.

Nothing in here calls out to the network -- it only reads the CSV that
fast_scraper.py already just wrote, and reads/writes its own JSON log.
"""

import csv
import json
import os
from datetime import datetime, timezone

PLACEMENTS_CSV = "ir_leaderboard_placements.csv"

# how many players count as "top" for board_takeover / aggregate_move
# purposes -- keeps the log from noting churn far down an unranked field
AGGREGATE_TRACK_DEPTH = 10

# an aggregate move smaller than this many positions isn't worth logging
MIN_AGGREGATE_MOVE = 1


def log_filename_for_window(start):
    """One file per competition, keyed by the window's start month --
    e.g. lotlb_2026_09.json. A new month's competition automatically
    gets a fresh file; nothing needs manual resetting."""
    return f"lotlb_{start.year}_{start.month:02d}.json"


def load_placements(csv_path=PLACEMENTS_CSV):
    """Returns (standings, by_board) mirroring the exact aggregation
    logic used client-side in leaderboard.html / x_post_expediter.html:
    standings = [{player, points, boards}], sorted by points descending.
    by_board = {board_name: [{player, rank, points}, ...]}, sorted by rank."""
    if not os.path.exists(csv_path):
        return [], {}

    totals = {}
    by_board = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            player = (row.get("player") or "").strip()
            board = (row.get("board") or "").strip()
            if not player or not board:
                continue
            try:
                rank = int(row.get("rank", 0) or 0)
            except ValueError:
                rank = 0
            try:
                points = int(row.get("points", 0) or 0)
            except ValueError:
                points = 0

            totals.setdefault(player, {"player": player, "points": 0, "boards": 0})
            totals[player]["points"] += points
            totals[player]["boards"] += 1

            by_board.setdefault(board, []).append({"player": player, "rank": rank, "points": points})

    standings = sorted(totals.values(), key=lambda s: s["points"], reverse=True)
    for board in by_board:
        by_board[board].sort(key=lambda r: r["rank"])

    return standings, by_board


def load_log(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_log(path, log):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)


def detect_board_takeovers(prev_by_board, curr_by_board):
    """A board's #1 spot changed hands since the last snapshot."""
    events = []
    for board, curr_rows in curr_by_board.items():
        if not curr_rows:
            continue
        curr_first = curr_rows[0]["player"]

        prev_rows = prev_by_board.get(board)
        if not prev_rows:
            continue  # board didn't exist last snapshot -- nothing to compare
        prev_first = prev_rows[0]["player"]

        if curr_first != prev_first:
            events.append({
                "type": "board_takeover",
                "board": board,
                "loser": prev_first,
                "winner": curr_first,
            })
    return events


def detect_aggregate_moves(prev_standings, curr_standings, depth=AGGREGATE_TRACK_DEPTH):
    """Players whose overall rank (by summed points) moved significantly
    among the top `depth` in either the old or new standings."""
    if not prev_standings:
        return []

    prev_rank = {s["player"]: i + 1 for i, s in enumerate(prev_standings)}
    curr_rank = {s["player"]: i + 1 for i, s in enumerate(curr_standings)}

    tracked_players = {s["player"] for s in curr_standings[:depth]} | {s["player"] for s in prev_standings[:depth]}

    events = []
    for player in tracked_players:
        old_r = prev_rank.get(player)
        new_r = curr_rank.get(player)
        if old_r is None or new_r is None or old_r == new_r:
            continue
        positions = old_r - new_r  # positive = moved up, negative = moved down
        if abs(positions) < MIN_AGGREGATE_MOVE:
            continue
        events.append({
            "type": "aggregate_move",
            "player": player,
            "direction": "up" if positions > 0 else "down",
            "positions": abs(positions),
            "old_rank": old_r,
            "new_rank": new_r,
        })
    return events


def update_movement_log(start, end, now):
    """Main entry point, called from orchestrate.py after a successful
    fast_scraper.py run. `start`/`end` are the current competition
    window's bounds (already computed by the caller); `now` is the
    current UTC timestamp for this run."""
    log_path = log_filename_for_window(start)
    standings, by_board = load_placements()

    log = load_log(log_path)
    is_fresh = log is None or log.get("competition_start") != start.isoformat()
    if is_fresh:
        print(f"movement_tracker: starting fresh log at {log_path}")
        log = {
            "competition_start": start.isoformat(),
            "competition_end": end.isoformat(),
            "snapshots": [],
            "movements": [],
        }

    prev_snapshot = log["snapshots"][-1] if log["snapshots"] else None

    new_movements = []
    if prev_snapshot:
        board_events = detect_board_takeovers(prev_snapshot["by_board"], by_board)
        aggregate_events = detect_aggregate_moves(prev_snapshot["standings"], standings)
        for ev in board_events + aggregate_events:
            ev["timestamp"] = now.isoformat()
            new_movements.append(ev)

    log["snapshots"].append({
        "timestamp": now.isoformat(),
        "standings": standings,
        "by_board": by_board,
    })
    log["movements"].extend(new_movements)

    save_log(log_path, log)
    print(f"movement_tracker: wrote {log_path} "
          f"({len(log['snapshots'])} snapshot(s), {len(new_movements)} new movement(s) this run, "
          f"{len(log['movements'])} total)")


if __name__ == "__main__":
    # manual test run: uses the real current competition window
    from competition_window import compute_competition_window
    now = datetime.now(timezone.utc)
    start, end = compute_competition_window(now)
    update_movement_log(start, end, now)
