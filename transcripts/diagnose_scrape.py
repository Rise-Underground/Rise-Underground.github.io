#!/usr/bin/env python3
"""
Diagnostic tool for scrape_new_episodes.py.

Prints exactly what yt-dlp sees when it fetches the channel's recent
uploads, and shows whether/why each tracked series' next-expected-episode
regex does or doesn't match anything in that list. Doesn't scrape or save
anything - read-only.

Usage:
    python diagnose_scrape.py
"""

import re
import unicodedata

import yt_dlp

CHANNEL_URL = "https://www.youtube.com/@InfinityRisingGame"
RECENT_VIDEOS_BATCH = 50

# Same series/expected-number info as the main script. Edit NEXT_EXPECTED
# below to whatever episode number you're trying to find.
SERIES = [
    {"name": "Cafe Rise", "next_expected": 158},
    {"name": "Origin Point", "next_expected": None},  # set a number to check this series too
]


def strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in normalized if not unicodedata.combining(c))


def build_title_regex(series_name: str, number: int) -> re.Pattern:
    name_pattern = re.escape(strip_accents(series_name)).replace(r"\ ", r"\s+")
    return re.compile(rf"\b{name_pattern}\D*\b0*{number}\b", re.IGNORECASE)


def fetch(url: str, label: str):
    print(f"\n=== Fetching via: {label} ===")
    print(f"URL: {url}")
    ydl_opts = {
        "extract_flat": "in_playlist",
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "playlistend": RECENT_VIDEOS_BATCH,
    }
    videos = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            print(f"Top-level type: {info.get('_type')}, title: {info.get('title')!r}")
            entries = info.get("entries", [])
            print(f"Top-level entries returned: {len(entries)}")
            for entry in entries:
                if entry is None:
                    continue
                if entry.get("_type") == "playlist" and "entries" in entry:
                    print(f"  -> nested playlist tab found: {entry.get('title')!r} ({len(entry['entries'])} entries)")
                    for sub in entry["entries"]:
                        if sub:
                            videos.append(sub)
                else:
                    videos.append(entry)
    except Exception as e:
        print(f"!!! Fetch failed: {type(e).__name__}: {e}")
        return []

    print(f"Total flat video entries collected: {len(videos)}")
    return videos


def main():
    # Try three variants of the channel URL, since YouTube's default tab
    # for a bare channel URL can behave inconsistently with yt-dlp.
    variants = [
        (CHANNEL_URL, "bare channel URL (default tab)"),
        (CHANNEL_URL.rstrip("/") + "/videos", "explicit /videos tab"),
        (CHANNEL_URL.rstrip("/") + "/streams", "explicit /streams tab (in case episodes are live/premiere uploads)"),
    ]

    all_results = {}
    for url, label in variants:
        videos = fetch(url, label)
        all_results[label] = videos

        print(f"\nFirst 15 titles from '{label}':")
        for v in videos[:15]:
            title = v.get("title")
            vid = v.get("id")
            print(f"  [{vid}] {title!r}")

    # Use whichever variant returned the most entries as the "best" list
  # for the regex-matching check below.
    best_label = max(all_results, key=lambda k: len(all_results[k]))
    best_videos = all_results[best_label]
    print(f"\n=== Using '{best_label}' ({len(best_videos)} entries) for match-checking ===")

    for series in SERIES:
        name = series["name"]
        number = series["next_expected"]
        if number is None:
            continue
        pattern = build_title_regex(name, number)
        print(f"\n[{name}] looking for episode {number}")
        print(f"  Regex: {pattern.pattern}")

        found = False
        for v in best_videos:
            raw_title = v.get("title") or ""
            norm_title = strip_accents(raw_title)
            if pattern.search(norm_title):
                print(f"  MATCH: [{v.get('id')}] {raw_title!r}")
                found = True

        if not found:
            print("  No match found. Closest titles containing the series name or number:")
            loose_name = re.compile(re.escape(strip_accents(name)), re.IGNORECASE)
            for v in best_videos:
                raw_title = v.get("title") or ""
                norm_title = strip_accents(raw_title)
                if loose_name.search(norm_title) or str(number) in norm_title:
                    print(f"    [{v.get('id')}] {raw_title!r}")


if __name__ == "__main__":
    main()
