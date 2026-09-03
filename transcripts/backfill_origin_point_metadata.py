#!/usr/bin/env python3
"""
backfill_origin_point_metadata.py

Existing Origin Point Episode N.json files were built from local .txt
transcripts and have no video_id/url -- so there's no way to build a
clickable timestamped YouTube link for OP# citations. This script fixes
that: for every "Origin Point Episode N.json" already on disk, it finds
the matching video on the channel by title, re-fetches real metadata +
a real timestamped transcript (same fetch logic as scrape_new_episodes.py),
and writes an updated copy with the same schema Cafe Rise/AMA episodes
already have (video_id, url, upload_date, duration_seconds, transcript
with real start/duration per segment, etc.).

Non-destructive: writes updated files into a sibling "Origin Point
Updated" folder rather than overwriting the originals in place, so you
can spot-check before replacing anything.

If an old file's "chapters" field was actually populated (empty in the
sample checked), that field is carried forward into the updated record
since the transcript refetch has no chapter data of its own.

Requirements:
    pip install yt-dlp youtube-transcript-api

Usage:
    python backfill_origin_point_metadata.py
    python backfill_origin_point_metadata.py --folder "C:\\path\\to\\Origin Point" --scan-limit 1000
"""

import argparse
import json
import re
from pathlib import Path

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
    CouldNotRetrieveTranscript,
    RequestBlocked,
    IpBlocked,
)

CHANNEL_URL = "https://www.youtube.com/@InfinityRisingGame"
LANGS_PREFERENCE = ["en"]
SERIES_NAME = "Origin Point"
DEFAULT_FOLDER = Path(r"C:\Users\19782\Desktop\Rise-Underground.github.io\transcripts\Origin Point")
DEFAULT_SCAN_LIMIT = 1000  # Origin Point episodes could be anywhere in upload history, not just recent

FILENAME_PATTERN = re.compile(r"^Origin Point Episode (\d+)\.json$")

_YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "socket_timeout": 15,
    "retries": 2,
    "extractor_retries": 1,
}
_ydl = yt_dlp.YoutubeDL(_YDL_OPTS)
_ytt_api = YouTubeTranscriptApi()


class BlockedError(Exception):
    """Raised when YouTube is actively blocking this IP -- distinct from 'no captions exist'."""
    pass


def get_all_videos(channel_url: str, limit: int) -> list[dict]:
    ydl_opts = {
        "extract_flat": "in_playlist",
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "playlistend": limit,
    }
    videos = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
        entries = info.get("entries", [])
        for entry in entries:
            if entry is None:
                continue
            if entry.get("_type") == "playlist" and "entries" in entry:
                for sub in entry["entries"]:
                    if sub:
                        videos.append(sub)
            else:
                videos.append(entry)
    return videos


def build_title_regex(series_name: str, number: int) -> re.Pattern:
    name_pattern = re.escape(series_name).replace(r"\ ", r"\s+")
    return re.compile(rf"\b{name_pattern}\D*\b0*{number}\b", re.IGNORECASE)


def find_matching_video(all_videos: list[dict], series_name: str, number: int) -> dict | None:
    pattern = build_title_regex(series_name, number)
    for entry in all_videos:
        title = entry.get("title") or ""
        if pattern.search(title):
            return entry
    return None


def get_full_metadata(video_id: str) -> dict:
    url = f"https://www.youtube.com/watch?v={video_id}"
    info = _ydl.extract_info(url, download=False)
    return {
        "video_id": video_id,
        "title": info.get("title"),
        "upload_date": info.get("upload_date"),
        "duration_seconds": info.get("duration"),
        "description": info.get("description"),
        "view_count": info.get("view_count"),
        "url": url,
    }


def get_transcript(video_id: str) -> list[dict] | None:
    try:
        fetched = _ytt_api.fetch(video_id, languages=LANGS_PREFERENCE)
        return [
            {"start": round(s.start, 2), "duration": round(s.duration, 2), "text": s.text}
            for s in fetched
        ]
    except NoTranscriptFound:
        try:
            transcript_list = _ytt_api.list(video_id)
            transcript = next(iter(transcript_list))
            fetched = transcript.fetch()
            return [
                {"start": round(s.start, 2), "duration": round(s.duration, 2), "text": s.text}
                for s in fetched
            ]
        except (RequestBlocked, IpBlocked) as e:
            raise BlockedError(str(e))
        except Exception as e:
            print(f"  ! No transcript available for {video_id}: {type(e).__name__}: {e}")
            return None
    except (RequestBlocked, IpBlocked) as e:
        raise BlockedError(str(e))
    except (TranscriptsDisabled, VideoUnavailable) as e:
        print(f"  ! {type(e).__name__} for {video_id} (captions genuinely unavailable)")
        return None
    except CouldNotRetrieveTranscript as e:
        print(f"  ! Could not retrieve transcript for {video_id}: {e}")
        return None
    except Exception as e:
        print(f"  ! Unexpected error fetching transcript for {video_id}: {type(e).__name__}: {e}")
        return None


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text or "").strip().lower()
    return re.sub(r"[-\s]+", "-", text)


def find_local_episodes(folder: Path) -> list[int]:
    numbers = []
    for f in folder.iterdir():
        m = FILENAME_PATTERN.match(f.name)
        if m:
            numbers.append(int(m.group(1)))
    return sorted(numbers)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--folder", type=Path, default=DEFAULT_FOLDER,
                     help="Folder containing existing 'Origin Point Episode N.json' files")
    ap.add_argument("--scan-limit", type=int, default=DEFAULT_SCAN_LIMIT,
                     help="How many channel uploads to scan for title matches")
    args = ap.parse_args()

    if not args.folder.exists():
        print(f"Folder not found: {args.folder}")
        return

    episode_numbers = find_local_episodes(args.folder)
    if not episode_numbers:
        print(f"No 'Origin Point Episode N.json' files found in {args.folder}")
        return

    print(f"Found {len(episode_numbers)} local Origin Point episode(s): {episode_numbers}")

    out_folder = args.folder.parent / "Origin Point Updated"
    out_folder.mkdir(exist_ok=True)

    print(f"Fetching up to {args.scan_limit} channel uploads to search for title matches...")
    all_videos = get_all_videos(CHANNEL_URL, args.scan_limit)
    print(f"Fetched {len(all_videos)} channel upload(s).\n")

    not_found = []
    failed = []
    succeeded = []

    for number in episode_numbers:
        print(f"[Origin Point {number}] searching for matching video...")
        match = find_matching_video(all_videos, SERIES_NAME, number)
        if not match:
            print(f"  Not found in the {len(all_videos)} scanned uploads. Skipping.\n")
            not_found.append(number)
            continue

        video_id = match.get("id") or match.get("url")
        print(f"  Matched video_id: {video_id} -- title: {match.get('title')}")

        try:
            meta = get_full_metadata(video_id)
        except Exception as e:
            print(f"  ! Failed to fetch metadata: {type(e).__name__}: {e}\n")
            failed.append(number)
            continue

        try:
            transcript = get_transcript(video_id)
        except BlockedError as e:
            print(f"  !!! YouTube appears to be blocking transcript requests from this IP: {e}")
            print("  Stopping here -- wait 15-30+ minutes, then re-run (already-done episodes will be skipped since their local files still show the old schema; re-run will just redo everyone, so best to note where this stopped).")
            break

        full_text = " ".join(seg["text"] for seg in transcript) if transcript else ""

        old_path = args.folder / f"Origin Point Episode {number}.json"
        old_chapters = []
        if old_path.exists():
            try:
                old_data = json.loads(old_path.read_text(encoding="utf-8"))
                old_chapters = old_data.get("chapters") or []
            except Exception:
                pass

        record = {
            **meta,
            "slug": slugify(meta.get("title", video_id)),
            "chapters": old_chapters,
            "transcript": transcript,
            "transcript_text": full_text,
            "has_transcript": transcript is not None,
        }

        out_path = out_folder / f"Origin Point Episode {number}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        print(f"  Saved to: {out_path}\n")
        succeeded.append(number)

    print("=" * 60)
    print(f"Done. {len(succeeded)} updated, {len(not_found)} not found, {len(failed)} failed.")
    if not_found:
        print(f"  Not found on channel: {not_found}")
    if failed:
        print(f"  Failed to fetch: {failed}")
    print(f"\nUpdated files are in: {out_folder}")
    print("Spot-check a few, then replace the originals if they look right.")


if __name__ == "__main__":
    main()
