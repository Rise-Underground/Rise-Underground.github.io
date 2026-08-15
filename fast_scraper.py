"""
Infinity Rising — Fast Leaderboard Aggregator (API-direct version)
=====================================================================

What changed from the old (browser-driven) scraper
-----------------------------------------------------
The old version drove a full Chromium browser through 50 separate page
loads and filter-clicks, taking minutes. This version was written after
inspecting the site's actual network traffic (via investigate_site.py)
and found that infinityrising.com's leaderboard pages just call a plain
JSON API in the background:

    https://gameapi.cornucopiasweb.io/players/holocaches/leaderboard
    https://gameapi.cornucopiasweb.io/players/aeroRaces/leaderboard
    https://gameapi.cornucopiasweb.io/players/races/leaderboard

No browser is needed — this script just calls those endpoints directly
with `requests`. That's the whole reason it's dramatically faster.

Bonus: this also finally solves the "exact competition window" problem.
Every endpoint takes startTime/endTime query params directly, so we can
request the REAL 3rd-Sunday-00:00-UTC-to-Saturday-23:59:59-UTC window
precisely, instead of guessing at the site's "Weekly" filter button.

Bonus #2: the Calido race API already returns vehicleManufacturer +
vehicleModel on every race record. That means ONE call per track
(3 calls total) returns every vehicle's data at once — we sort it into
the 14 per-vehicle boards ourselves in Python, instead of needing 42
separate filtered page visits.

Every board is tracked, even empty ones
------------------------------------------
For Calido, an extra all-time (wide date range) query per track finds
every vehicle that has EVER raced there, so a vehicle nobody has
touched during the current test period still shows up as a known
board with 0 placements — rather than silently not existing. This
writes a second file, ir_leaderboard_boards.csv, listing every board
(all 50) with its placement count, so it's easy to see which ones are
still open for someone to be first on.

IMPORTANT — please verify before trusting this for real standings
---------------------------------------------------------------------
Confirmed competition rules (per direct confirmation):
  - Holocache: ranked by best (fastest) time only — NOT by number of
    holocaches collected.
  - Aero Trails: 6 courses (courseId 1-6), best time per course.
  - Calido: 3 tracks x 14 vehicles = 42 boards, best time per board.
  - No lap-time boards — every ranking uses total time
    (timeTakenSeconds / totalRaceTimeMs), never bestLapTimeMs, even
    though the API includes lap-level data in each race record.
  - Window: the current test period ("weekly" — see PERIOD_START/END
    below), not all-time.

Still worth spot-checking against the live site:
  - No authentication appeared to be required for these GET calls in
    the captured traffic — if this script starts getting 401/403
    errors, the site may require a session cookie or auth header we
    didn't capture, and we'd need to fall back to the browser version.
  - AERO_TRAILS_COURSE_IDS assumes course IDs are exactly 1-6
    sequentially — worth confirming against the site's own Course
    filter dropdown if that's not the case.

Run
---
    pip install requests
    python fast_scraper.py
"""

import os
import re
import requests
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from competition_window import compute_competition_window

API_BASE = "https://gameapi.cornucopiasweb.io/players"

# Where the results CSV gets written.
OUTPUT_CSV_PATH = r"C:\Users\19782\Desktop\IR Leader board\repo\ir_leaderboard_placements.csv"

CALIDO_TRACKS = {
    "Calido Yellow": "calido_yellow",
    "Calido Red": "calido_red",
    "Calido Purple": "calido_purple",
}

# Confirmed straight from the site's own "Vehicle" filter checkboxes on
# the Calido Valley Raceway leaderboard page — this is the ground-truth
# list of every vehicle valid for this leaderboard, independent of race
# history. Solves the "vehicle nobody has ever raced" gap, since this
# doesn't depend on any race data existing at all.
CALIDO_VEHICLES = [
    "Astro IV",
    "Bubblejett Bonanza 2023",
    "Bubblejett Bonanza OG Custom 2023",
    "Bubblejett Sprinter 2022",
    "Bubblejett Sprinter OG Custom 2022",
    "Bubblejett Super Phantom",
    "GTi Javelin 2022",
    "Kazekura Shinobi-X",
    "Rando's Metalworks Sunset Speeder",
    "Valkyrie F9-R",
    "Valley Raceworx T1-A",
    "Valley Raceworx T1-B",
    "Valley Raceworx T1-C",
    "Valley Raceworx T3 2023",
]

AERO_TRAILS_COURSES = {
    # Confirmed directly from the site's Course filter HTML
    # (each checkbox's id="courseId_N" attribute) — note 6 is skipped
    # entirely, it jumps from 5 to 7.
    1: "Calido",
    2: "Solace 3",
    3: "Solace 2",
    4: "Solace 1",
    5: "Pavilion",
    7: "Hub City",
}

POINTS_FOR_RANK = {i: (11 - i) for i in range(1, 11)}  # 1st=10 ... 10th=1

# ---------------------------------------------------------------------
# Competition window: the real 3rd-Sunday-00:00-UTC-to-following-
# Saturday-23:59:59-UTC window. Using the FIXED window boundaries
# (not "now") means every scrape during a competition is scoped
# identically, and the very first scrape of a new competition
# automatically excludes the previous one's data — no manual reset
# step needed.
# ---------------------------------------------------------------------
def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

_window_start, _window_end = compute_competition_window()
PERIOD_START = iso(_window_start)
PERIOD_END = iso(_window_end)


def fetch_all(url, params, results_key="values"):
    """Fetches all pages of results (handles the API's offset/limit
    pagination) and returns the combined list of raw records."""
    all_values = []
    offset = 0
    limit = 100
    while True:
        page_params = {**params, "limit": limit, "offset": offset}
        resp = requests.get(url, params=page_params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        values = data.get(results_key, [])
        all_values.extend(values)
        total = data.get("total", len(all_values))
        offset += limit
        if offset >= total or not values:
            break
    return all_values


def dedupe_best_per_player(records, score_key, ascending=True):
    """Keeps only each player's single best record (by score_key),
    since the API can return multiple races per player."""
    best = {}
    for r in records:
        player_id = r.get("playerId")
        score = r.get(score_key)
        if score is None or player_id is None:
            continue
        if player_id not in best:
            best[player_id] = r
        else:
            current = best[player_id][score_key]
            if (ascending and score < current) or (not ascending and score > current):
                best[player_id] = r
    values = list(best.values())
    values.sort(key=lambda r: r[score_key], reverse=not ascending)
    return values


def display_name(record):
    profile = record.get("playerProfile", {})
    return profile.get("displayName", "UNKNOWN")


def scrape_holocache(placements, all_boards):
    print("Fetching Holocache...")
    records = fetch_all(
        f"{API_BASE}/holocaches/leaderboard",
        {"startTime": PERIOD_START, "endTime": PERIOD_END, "orderByDirection": "asc"},
    )
    # Ranked purely by best (fastest) time — same convention as every
    # other board (Aero Trails / Calido). NOT by holocachesCollected
    # count — that field exists in the API response but isn't used for
    # ranking here per confirmed competition rules.
    top10 = dedupe_best_per_player(records, "timeTakenSeconds", ascending=True)[:10]
    print(f"  -> {len(top10)} rows")
    all_boards["Holocache"] = len(top10)
    for i, r in enumerate(top10, start=1):
        placements.append((display_name(r), "Holocache", i, POINTS_FOR_RANK[i]))


# Confirmed directly from the site's Vehicle filter checkbox id
# attributes (id="vehicleModel_T1-A" etc.) — this is the exact raw
# "vehicleModel" key the site/API uses, mapped to the canonical display
# name. No guessing or fuzzy matching needed; this is ground truth.
VEHICLE_MODEL_TO_CANONICAL = {
    "Astro IV": "Astro IV",
    "Bonanza": "Bubblejett Bonanza 2023",
    "Bonanza OG Custom": "Bubblejett Bonanza OG Custom 2023",
    "Sprinter": "Bubblejett Sprinter 2022",
    "Sprinter OG Custom": "Bubblejett Sprinter OG Custom 2022",
    "Super Phantom": "Bubblejett Super Phantom",
    "Javelin": "GTi Javelin 2022",
    "Shinobi-X": "Kazekura Shinobi-X",
    "Sunset Speeder": "Rando's Metalworks Sunset Speeder",
    "F9-R": "Valkyrie F9-R",
    "T1-A": "Valley Raceworx T1-A",
    "T1-B": "Valley Raceworx T1-B",
    "T1-C": "Valley Raceworx T1-C",
    "T3": "Valley Raceworx T3 2023",
}


def match_canonical_vehicle(manufacturer, model):
    """Maps an API vehicleManufacturer+vehicleModel pair to one of the
    confirmed canonical vehicle names using the exact lookup above.
    Returns None if the model is genuinely unrecognized — callers must
    handle None by keeping the raw API name rather than dropping data
    (e.g. a brand-new vehicle the game added that we haven't seen yet)."""
    model_clean = (model or "").strip()
    if model_clean in VEHICLE_MODEL_TO_CANONICAL:
        return VEHICLE_MODEL_TO_CANONICAL[model_clean]

    # Fallback: case-insensitive / whitespace-tolerant exact match, in
    # case the API varies casing or spacing slightly from the checkbox id.
    normalized = re.sub(r"\s+", " ", model_clean).strip().lower()
    for key, canonical_name in VEHICLE_MODEL_TO_CANONICAL.items():
        if key.lower() == normalized:
            return canonical_name
    return None  # genuinely unrecognized — caller keeps the raw name


def scrape_aero_trails(placements, all_boards):
    for course_id, course_name in AERO_TRAILS_COURSES.items():
        board_name = f"Aero Trails — {course_name}"
        print(f"Fetching {board_name}...")
        records = fetch_all(
            f"{API_BASE}/aeroRaces/leaderboard",
            {
                "courseId": course_id,
                "startTime": PERIOD_START,
                "endTime": PERIOD_END,
                "orderByDirection": "asc",
                "uniqueResults": "false",
            },
        )
        top10 = dedupe_best_per_player(records, "timeTakenSeconds", ascending=True)[:10]
        print(f"  -> {len(top10)} rows")
        all_boards[board_name] = len(top10)
        for i, r in enumerate(top10, start=1):
            placements.append((display_name(r), board_name, i, POINTS_FOR_RANK[i]))


def scrape_calido(placements, all_boards):
    for track_label, track_param in CALIDO_TRACKS.items():
        print(f"Fetching {track_label} (test-period results, all vehicles in one call)...")
        records = fetch_all(
            f"{API_BASE}/races/leaderboard",
            {
                "track": track_param,
                "sortBy": "raceTime",
                "startTime": PERIOD_START,
                "endTime": PERIOD_END,
                "orderByDirection": "asc",
                "uniqueResults": "false",
            },
        )
        print(f"  -> {len(records)} total race records this period, sorting into per-vehicle boards...")

        by_vehicle = defaultdict(list)
        unmatched_names = set()
        for r in records:
            manufacturer = r.get("vehicleManufacturer", "?")
            model = r.get("vehicleModel", "?")
            canonical = match_canonical_vehicle(manufacturer, model)
            if canonical:
                by_vehicle[canonical].append(r)
            else:
                # Never silently drop data — keep the raw API name as its
                # own board so nothing gets lost, and flag it for review.
                raw_name = f"{manufacturer} {model}"
                by_vehicle[raw_name].append(r)
                unmatched_names.add(raw_name)

        if unmatched_names:
            print(f"  !! {len(unmatched_names)} vehicle name(s) didn't match the known list "
                  f"(kept as-is, worth checking): {sorted(unmatched_names)}")

        # Walk the confirmed 14-vehicle canonical list — guaranteed
        # complete regardless of race history — plus any unmatched extras.
        all_vehicle_names = list(CALIDO_VEHICLES) + sorted(unmatched_names)
        for vehicle in all_vehicle_names:
            board_name = f"{track_label} — {vehicle}"
            vehicle_records = by_vehicle.get(vehicle, [])
            top10 = dedupe_best_per_player(vehicle_records, "totalRaceTimeMs", ascending=True)[:10]
            all_boards[board_name] = len(top10)
            for i, r in enumerate(top10, start=1):
                placements.append((display_name(r), board_name, i, POINTS_FOR_RANK[i]))


def main():
    placements = []
    all_boards = {}  # board_name -> number of placements found (0 = open/unclaimed)

    scrape_holocache(placements, all_boards)
    scrape_aero_trails(placements, all_boards)
    scrape_calido(placements, all_boards)

    totals = {}
    for name, board, rank, points in placements:
        totals[name] = totals.get(name, 0) + points
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)

    print("\n=== OVERALL TOP 10 (by aggregate points across all boards) ===")
    for i, (name, pts) in enumerate(ranked[:10], start=1):
        print(f"{i}. {name} — {pts} pts")

    open_boards = [b for b, count in all_boards.items() if count == 0]
    print(f"\n{len(all_boards)} total boards tracked, {len(open_boards)} currently open (0 placements)")

    os.makedirs(os.path.dirname(OUTPUT_CSV_PATH), exist_ok=True)
    with open(OUTPUT_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        f.write("player,board,rank,points\n")
        for name, board, rank, points in placements:
            f.write(f'"{name}","{board}",{rank},{points}\n')
    print(f"\nFull placements written to {OUTPUT_CSV_PATH}")
    print(f"Total placements recorded: {len(placements)}")

    boards_csv_path = os.path.join(os.path.dirname(OUTPUT_CSV_PATH), "ir_leaderboard_boards.csv")
    with open(boards_csv_path, "w", newline="", encoding="utf-8") as f:
        f.write("board,placements_count\n")
        for board, count in sorted(all_boards.items()):
            f.write(f'"{board}",{count}\n')
    print(f"Full board list (including open/empty ones) written to {boards_csv_path}")


if __name__ == "__main__":
    main()
