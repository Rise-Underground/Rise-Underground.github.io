"""
Reads ir_leaderboard_placements.csv (same file leaderboard.html reads) and
aggregates it into standings, matching the exact logic in
leaderboard.html's buildStandings() JS function -- sum points per player,
sort descending.

Also handles snapshotting standings between runs so the Final Day
"movement" templates can detect real rank changes, not just re-fire on
every run.
"""

import csv
import json
import os


PLACEMENTS_CSV = "ir_leaderboard_placements.csv"
SNAPSHOT_PATH = "x_standings_snapshot.json"


def load_standings(csv_path=PLACEMENTS_CSV):
    """Returns a list of {name, points} dicts, sorted by points descending.
    Mirrors leaderboard.html's buildStandings() exactly: sum points per
    player across all their board placements, then sort."""
    if not os.path.exists(csv_path):
        return []

    by_player = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            player = row.get("player", "").strip()
            if not player:
                continue
            try:
                points = int(row.get("points", 0) or 0)
            except ValueError:
                points = 0
            by_player.setdefault(player, 0)
            by_player[player] += points

    standings = [{"name": name, "points": pts} for name, pts in by_player.items()]
    standings.sort(key=lambda s: s["points"], reverse=True)
    return standings


def top_n(standings, n=3):
    """Returns the top N as a flat dict ready for str.format(), e.g.
    top1_name, top1_points, top2_name, top2_points, ... Missing ranks
    (fewer than N players) fall back to placeholder text so templates
    don't crash on a near-empty leaderboard."""
    out = {}
    for i in range(n):
        rank = i + 1
        if i < len(standings):
            out[f"top{rank}_name"] = standings[i]["name"]
            out[f"top{rank}_points"] = standings[i]["points"]
        else:
            out[f"top{rank}_name"] = "—"
            out[f"top{rank}_points"] = 0
    return out


def load_snapshot(path=SNAPSHOT_PATH):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_snapshot(standings, path=SNAPSHOT_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(standings, f, indent=2)


def detect_movement(previous_standings, current_standings, top_n_size=3):
    """
    Compares two standings snapshots and returns a movement event, or
    None if nothing worth calling out changed.

    Priority: a NEW top-3 entrant is more newsworthy than a same-top-3
    reshuffle, so that's checked first.

    Returns one of:
      {"type": "entered_top3", "name": ..., "new_rank": ..., "positions_moved": ...}
      {"type": "moved_up", "name": ..., "positions_moved": ...}
      None
    """
    if not previous_standings:
        return None

    prev_rank = {s["name"]: i + 1 for i, s in enumerate(previous_standings)}
    curr_rank = {s["name"]: i + 1 for i, s in enumerate(current_standings)}

    prev_top3_names = {s["name"] for s in previous_standings[:top_n_size]}

    # Check for a new top-3 entrant first (most newsworthy)
    for i, s in enumerate(current_standings[:top_n_size]):
        name = s["name"]
        new_rank = i + 1
        if name not in prev_top3_names:
            old_rank = prev_rank.get(name)
            positions_moved = (old_rank - new_rank) if old_rank else new_rank
            return {
                "type": "entered_top3",
                "name": name,
                "new_rank": new_rank,
                "positions_moved": max(positions_moved, 1),
            }

    # Otherwise, look for the single biggest riser anywhere in the field
    best_name, best_gain = None, 0
    for name, new_r in curr_rank.items():
        old_r = prev_rank.get(name)
        if old_r is None:
            continue
        gain = old_r - new_r
        if gain > best_gain:
            best_gain = gain
            best_name = name

    if best_name and best_gain > 0:
        return {
            "type": "moved_up",
            "name": best_name,
            "positions_moved": best_gain,
        }

    return None
