#!/usr/bin/env python3
"""
Check the channel for new episodes of tracked series (Cafe Rise, Origin Point)
and scrape any that are newer than what's already saved locally.

For each series:
    1. Look at the local output folder to find the highest episode number
       already saved.
    2. Compute the next expected episode number (highest + 1).
    3. Scan a batch of the channel's recent uploads for a title matching
       "<series name> <next number>" (as a whole number, so 157 won't
       false-match inside 1157).
    4. If found, scrape full metadata + transcript and save it.
    5. If not found, skip that series this run - no error, nothing new yet.

Designed to run unattended (e.g. via Task Scheduler) with no prompts.

Requirements:
    pip install yt-dlp youtube-transcript-api

Usage:
    python scrape_new_episodes.py
"""

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

# ---- CONFIG ----
CHANNEL_URL = "https://www.youtube.com/@InfinityRisingGame"
LANGS_PREFERENCE = ["en"]
RECENT_VIDEOS_BATCH = 50  # how many recent uploads to scan per run

SERIES = [
    {
        "name": "Cafe Rise",
        "folder": Path("Cafe Rise"),
        "filename_template": "Cafe Rise Episode {n}.json",
    },
    {
        "name": "Origin Point",
        "folder": Path("Origin Point"),
        "filename_template": "Origin Point Episode {n}.json",
    },
]

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
    """Raised when YouTube is actively blocking this IP - distinct from 'no captions exist'."""
    pass


def get_recent_videos(channel_url: str, limit: int) -> list[dict]:
    """Fetch a batch of the channel's most recent uploads (id + title only, fast)."""
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


def get_full_metadata(video_id: str) -> dict:
    """Fetch full metadata (title, upload date, duration, description) for a single video."""
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
    """Fetch transcript with timestamps. Returns None if genuinely unavailable, raises BlockedError if IP-blocked."""
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


def get_next_expected_number(series: dict) -> int:
    """Look at saved files in the series folder and return highest_saved + 1 (1 if none saved)."""
    folder = series["folder"]
    if not folder.exists():
        return 1

    # Turn "Cafe Rise Episode {n}.json" into a regex capturing n
    pattern_str = re.escape(series["filename_template"]).replace(r"\{n\}", r"(\d+)")
    pattern = re.compile(f"^{pattern_str}$")

    highest = 0
    for f in folder.iterdir():
        m = pattern.match(f.name)
        if m:
            highest = max(highest, int(m.group(1)))
    return highest + 1


def build_title_regex(series_name: str, number: int) -> re.Pattern:
    """Match series name followed by the exact number, as a whole number (not a substring of a larger one)."""
    name_pattern = re.escape(series_name).replace(r"\ ", r"\s+")
    return re.compile(rf"\b{name_pattern}\D*\b0*{number}\b", re.IGNORECASE)


def find_matching_video(recent_videos: list[dict], series_name: str, number: int) -> dict | None:
    pattern = build_title_regex(series_name, number)
    for entry in recent_videos:
        title = entry.get("title") or ""
        if pattern.search(title):
            return entry
    return None


def scrape_and_save(series: dict, number: int, video_id: str):
    folder = series["folder"]
    folder.mkdir(exist_ok=True)

    meta = get_full_metadata(video_id)
    print(f"  Title: {meta.get('title')}")

    try:
        transcript = get_transcript(video_id)
    except BlockedError as e:
        print(f"  !!! YouTube appears to be blocking transcript requests from this IP: {e}")
        print("  Skipping this series for now. Wait 15-30+ minutes, then re-run.")
        return False

    full_text = " ".join(seg["text"] for seg in transcript) if transcript else ""

    record = {
        **meta,
        "slug": slugify(meta.get("title", video_id)),
        "transcript": transcript,
        "transcript_text": full_text,
        "has_transcript": transcript is not None,
    }

    out_path = folder / series["filename_template"].format(n=number)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    print(f"  Saved to: {out_path}")
    if transcript is None:
        print("  Note: no transcript was available for this video.")
    return True


def main():
    print(f"Fetching {RECENT_VIDEOS_BATCH} most recent uploads from {CHANNEL_URL} ...")
    recent_videos = get_recent_videos(CHANNEL_URL, RECENT_VIDEOS_BATCH)
    print(f"Fetched {len(recent_videos)} recent uploads.\n")

    for series in SERIES:
        name = series["name"]
        next_num = get_next_expected_number(series)
        print(f"[{name}] looking for episode {next_num} ...")

        match = find_matching_video(recent_videos, name, next_num)
        if not match:
            print(f"[{name}] no matching video found in the {len(recent_videos)} most recent uploads. Nothing new.\n")
            continue

        video_id = match.get("id") or match.get("url")
        print(f"[{name}] found candidate: {video_id}")
        scrape_and_save(series, next_num, video_id)
        print()


if __name__ == "__main__":
    main()
