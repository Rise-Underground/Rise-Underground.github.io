#!/usr/bin/env python3
"""
process_episode_citations.py

For each episode transcript (Cafe Rise CC#, Origin Point OP#, the two
one-off AI/AMA episodes), asks Claude to:

  1. VERIFY every doc bullet that cites this episode -- was the subject
     actually discussed (even if reworded by consolidation)? If yes,
     find the timestamp it starts at.
  2. FIND GAPS -- anything discussed in this episode that isn't
     reasonably covered anywhere in the existing 755-item doc. Told to
     defer to your consolidation: when in doubt, treat it as already
     covered rather than flagging it.

T-Doc (tokenomics) citations are NOT handled here -- see
check_tokenomics_citations.py for that separate, one-time pass.

Stops after --limit NEW episodes per run (default 5) so you can check
quality/cost before committing to the rest. Already-processed episodes
are tracked in citation_check_state.json and skipped on the next run --
just re-run the same command (or pass a higher --limit) to continue.

REQUIRED EDITS BEFORE RUNNING -- see the CONFIG block below:
  - Confirm CAFE_RISE_FOLDER / ORIGIN_POINT_FOLDER / AMA_FOLDER paths
    match your actual folder layout.
  - Fill in AMA_TRANSCRIPT_FILE with the real filename for the "AMA"
    citation (AI_TRANSCRIPT_FILE is already filled in from the sample
    you provided).

Requirements:
    pip install anthropic

Usage:
    python process_episode_citations.py
    python process_episode_citations.py --limit 20
    python process_episode_citations.py --limit 999   # do everything left
"""

import argparse
import json
import re
import sys
from pathlib import Path

import anthropic

# ---------------------------------------------------------------------------
# CONFIG -- check these paths/filenames before running
# ---------------------------------------------------------------------------
TRANSCRIPTS_ROOT = Path(r"C:\Users\19782\Desktop\Rise-Underground.github.io\transcripts")
CAFE_RISE_FOLDER = TRANSCRIPTS_ROOT / "Cafe_Rise"
ORIGIN_POINT_FOLDER = TRANSCRIPTS_ROOT / "Origin Point"
AMA_FOLDER = TRANSCRIPTS_ROOT / "AMAs"

# AI and AMA are the SAME single episode (the AI Companion AMA Leak) --
# not two separate ones. Both citation codes resolve to this one file.
AI_TRANSCRIPT_FILE = AMA_FOLDER / "Rise Live - AI Companion AMA Leak.json"
CITATION_ALIASES = {"AMA": "AI"}

ARCHIVE_DATA_FILE = Path("archive_data.json")  # the 755-item doc export, ships alongside this script

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 16000  # CC1-style episodes can have 150+ citations to verify in one response;
                     # 4096 was silently truncating those (Haiku 4.5 supports up to 64k output)

STATE_FILE = Path("citation_check_state.json")
CITATION_INDEX_FILE = Path("citation_index.json")
UNVERIFIED_FILE = Path("citation_unverified.json")
ADDITIONS_FILE = Path("possible_additions.json")
FAILED_RESPONSES_FILE = Path("citation_check_failed_responses.json")

CITATION_RE = re.compile(r'\(((?:CC\d+|OP\d+|AMA|AI|T-Doc)(?:,\s*(?:CC\d+|OP\d+|AMA|AI|T-Doc))*)\)')


# ---------------------------------------------------------------------------
# Loading the doc's 755 items and building the citation -> items index
# ---------------------------------------------------------------------------
def load_archive_items():
    data = json.loads(ARCHIVE_DATA_FILE.read_text(encoding="utf-8"))
    flat = []
    for cat in data:
        header = cat["label"]
        for item in cat.get("items", []):
            desc = item.get("desc") or ""
            citations = set()
            for m in CITATION_RE.finditer(desc):
                citations.update(c.strip() for c in m.group(1).split(","))
            citations = sorted(citations)
            flat.append({
                "header": header,
                "name": item.get("name"),
                "desc": desc,
                "status": item.get("status"),
                "citations": citations,
            })
    return flat


def build_citation_index(items):
    index = {}
    for it in items:
        for c in it["citations"]:
            if c == "T-Doc":
                continue  # handled separately by check_tokenomics_citations.py
            c = CITATION_ALIASES.get(c, c)
            index.setdefault(c, []).append(it)
    return index


def build_known_topics_block(items):
    """Compact index of every item (name + one-line gist), reused verbatim
    across every call for the gap-finding job -- NOT the full description,
    to keep this block cheap regardless of how many episodes get processed."""
    lines = []
    for it in items:
        gist = (it["desc"] or "")[:100].replace("\n", " ")
        lines.append(f"- [{it['header']}] {it['name']}: {gist}...")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Discovering episodes on disk
# ---------------------------------------------------------------------------
def discover_cc_episodes():
    """Returns dict: 'CC{n}' -> list of (part_number_or_None, filepath), sorted."""
    if not CAFE_RISE_FOLDER.exists():
        print(f"WARNING: {CAFE_RISE_FOLDER} not found -- no CC episodes will be processed.")
        return {}
    single_pattern = re.compile(r"^Cafe Rise Episode (\d+)\.json$", re.IGNORECASE)
    part_pattern = re.compile(r"^Cafe Rise Episode (\d+) part (\d+)\.json$", re.IGNORECASE)

    episodes = {}
    for f in CAFE_RISE_FOLDER.iterdir():
        m = part_pattern.match(f.name)
        if m:
            n, part = int(m.group(1)), int(m.group(2))
            episodes.setdefault(f"CC{n}", []).append((part, f))
            continue
        m = single_pattern.match(f.name)
        if m:
            n = int(m.group(1))
            episodes.setdefault(f"CC{n}", []).append((None, f))

    for code in episodes:
        episodes[code].sort(key=lambda t: (t[0] is None, t[0]))
    return dict(sorted(episodes.items(), key=lambda kv: int(kv[0][2:])))


def discover_op_episodes():
    if not ORIGIN_POINT_FOLDER.exists():
        print(f"WARNING: {ORIGIN_POINT_FOLDER} not found -- no OP episodes will be processed.")
        return {}
    pattern = re.compile(r"^Origin Point Episode (\d+)\.json$", re.IGNORECASE)
    episodes = {}
    for f in ORIGIN_POINT_FOLDER.iterdir():
        m = pattern.match(f.name)
        if m:
            n = int(m.group(1))
            episodes[f"OP{n}"] = [(None, f)]
    return dict(sorted(episodes.items(), key=lambda kv: int(kv[0][2:])))


def discover_special_episodes():
    episodes = {}
    if AI_TRANSCRIPT_FILE.exists():
        episodes["AI"] = [(None, AI_TRANSCRIPT_FILE)]
    else:
        print(f"WARNING: AI_TRANSCRIPT_FILE not found at {AI_TRANSCRIPT_FILE} -- "
              f"skipping the AI/AMA citation.")
    return episodes


# ---------------------------------------------------------------------------
# Formatting a transcript (or multi-part transcript) for the prompt
# ---------------------------------------------------------------------------
def fmt_timestamp(seconds):
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def seg_seconds(seg):
    if seg.get("start_seconds") is not None:
        return seg["start_seconds"]
    if isinstance(seg.get("start"), (int, float)):
        return seg["start"]
    return None


def load_transcript_block(filepath, part_label):
    data = json.loads(filepath.read_text(encoding="utf-8"))
    url = data.get("url") or ""
    title = data.get("title") or filepath.stem
    lines = [f"=== {part_label} -- \"{title}\" (video: {url}) ==="]
    for seg in data.get("transcript") or []:
        secs = seg_seconds(seg)
        ts = fmt_timestamp(secs) if secs is not None else "?:??"
        lines.append(f"[{ts}] {seg.get('text', '')}")
    return "\n".join(lines), url, title


def build_episode_context(parts):
    """parts: list of (part_number_or_None, filepath). Returns (full_text, part_urls dict)."""
    blocks = []
    part_urls = {}
    for part_num, filepath in parts:
        label = f"PART {part_num}" if part_num else "FULL EPISODE"
        block, url, title = load_transcript_block(filepath, label)
        blocks.append(block)
        part_urls[part_num or 1] = {"url": url, "title": title}
    return "\n\n".join(blocks), part_urls


# ---------------------------------------------------------------------------
# The API call
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are helping verify a community-maintained feature-tracking \
document for a video game (Infinity Rising) against the podcast/AMA episode \
transcripts it was built from.

The document's bullet points were manually CONSOLIDATED from many episodes -- \
several small mentions across different moments often got merged into one \
bullet. When checking whether a bullet's subject was discussed in THIS \
episode, judge the SPIRIT of the match, not exact wording. If the transcript \
discusses that general subject/feature, count it as verified even if the \
bullet's exact phrasing differs.

EVERY SINGLE bullet listed under "BULLETS CITING THIS EPISODE" below MUST \
appear in either "verified" or "unverified" -- never both, never neither. \
If you are unsure or the match is weak, put it in "unverified" with a reason \
explaining the uncertainty -- do NOT simply omit an item because you're not \
confident. A skipped item is worse than a low-confidence guess: it looks \
like the check was never even run. Before finalizing your answer, count the \
bullets you were given and count your verified+unverified entries -- they \
must match exactly.

For the gap-finding task, you're given a compact index of ALL ~755 existing \
bullets across the whole document (not just this episode's). Defer to the \
existing consolidation: if a topic in this episode is arguably a sub-detail, \
rephrasing, or minor variant of ANY existing bullet (not just ones citing this \
episode), do NOT flag it as a gap. Only flag things with no reasonable home \
in the existing document.

Always respond with ONLY a single JSON object, no prose before or after, \
matching exactly this shape:

{
  "verified": [
    {"header": "...", "item_name": "...", "part": 1, "timestamp_seconds": 123, \
"confidence": "high|medium|low", "note": "one short sentence why this counts as a match"}
  ],
  "unverified": [
    {"header": "...", "item_name": "...", "reason": "one short sentence why you could not find this"}
  ],
  "possible_additions": [
    {"subject": "...", "part": 1, "timestamp_seconds": 456, \
"suggested_header": "...", "confidence": "high|medium|low", "note": "one short sentence"}
  ]
}

"part" should be the part number for multi-part episodes (1 or 2), or 1 for \
single-part episodes. timestamp_seconds must be an integer, the point where \
that discussion actually starts (not just where the episode section begins).
"""


def call_claude(client, episode_code, episode_title, transcript_text, relevant_items, known_topics_block):
    if relevant_items:
        items_block = "\n\n".join(
            f"- HEADER: {it['header']}\n  NAME: {it['name']}\n  DESC: {it['desc']}"
            for it in relevant_items
        )
    else:
        items_block = "(No existing bullets cite this episode.)"

    user_content = [
        {
            "type": "text",
            "text": (
                f"EPISODE: {episode_code} -- \"{episode_title}\"\n\n"
                f"BULLETS CITING THIS EPISODE (verify these):\n{items_block}\n\n"
                f"KNOWN-TOPICS INDEX (all existing bullets, for gap-finding only -- "
                f"do not re-verify these against this episode, just use them to judge novelty):\n"
            ),
        },
        {
            "type": "text",
            "text": known_topics_block,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": f"\n\nFULL TRANSCRIPT:\n{transcript_text}",
        },
    ]

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return response.content[0].text


def parse_json_response(raw_text):
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in response")
    return json.loads(raw_text[start:end + 1])


# ---------------------------------------------------------------------------
# State + output file helpers
# ---------------------------------------------------------------------------
def load_json_list(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []


def save_json_list(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"done": []}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def make_youtube_link(url, timestamp_seconds):
    if not url or timestamp_seconds is None:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}t={int(timestamp_seconds)}s"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=5, help="Max NEW episodes to process this run (default 5)")
    args = ap.parse_args()

    if not ARCHIVE_DATA_FILE.exists():
        print(f"ERROR: {ARCHIVE_DATA_FILE} not found. This file must sit next to the script.")
        sys.exit(1)

    items = load_archive_items()
    citation_index_map = build_citation_index(items)
    known_topics_block = build_known_topics_block(items)
    print(f"Loaded {len(items)} doc items, {len(citation_index_map)} distinct citation codes cited.")

    episodes = {}
    episodes.update(discover_cc_episodes())
    episodes.update(discover_op_episodes())
    episodes.update(discover_special_episodes())
    print(f"Discovered {len(episodes)} episode(s) on disk.")

    state = load_state()
    done = set(state["done"])
    todo = [code for code in episodes if code not in done]
    print(f"{len(done)} already done, {len(todo)} remaining.")

    batch = todo[: args.limit]
    if not batch:
        print("Nothing to do -- all discovered episodes are already processed.")
        return

    print(f"Processing {len(batch)} episode(s) this run: {batch}\n")

    client = anthropic.Anthropic()

    citation_index = load_json_list(CITATION_INDEX_FILE)
    unverified = load_json_list(UNVERIFIED_FILE)
    additions = load_json_list(ADDITIONS_FILE)
    failed = load_json_list(FAILED_RESPONSES_FILE)

    for code in batch:
        parts = episodes[code]
        relevant_items = citation_index_map.get(code, [])
        print(f"[{code}] {len(parts)} file(s), {len(relevant_items)} bullet(s) to verify...")

        try:
            transcript_text, part_urls = build_episode_context(parts)
        except Exception as e:
            print(f"  ! Failed to load transcript file(s): {type(e).__name__}: {e}")
            continue

        episode_title = next(iter(part_urls.values()))["title"]

        try:
            raw = call_claude(client, code, episode_title, transcript_text, relevant_items, known_topics_block)
            result = parse_json_response(raw)
        except Exception as e:
            print(f"  ! API call or JSON parse failed: {type(e).__name__}: {e}")
            failed.append({"episode": code, "error": str(e)})
            save_json_list(FAILED_RESPONSES_FILE, failed)
            continue

        for v in result.get("verified", []):
            part_info = part_urls.get(v.get("part", 1), part_urls.get(1))
            link = make_youtube_link(part_info["url"], v.get("timestamp_seconds"))
            citation_index.append({
                "header": v.get("header"),
                "item_name": v.get("item_name"),
                "citation": code,
                "episode_title": episode_title,
                "timestamp_seconds": v.get("timestamp_seconds"),
                "timestamp_display": fmt_timestamp(v["timestamp_seconds"]) if v.get("timestamp_seconds") is not None else None,
                "link": link,
                "confidence": v.get("confidence"),
                "note": v.get("note"),
            })

        for u in result.get("unverified", []):
            unverified.append({
                "header": u.get("header"),
                "item_name": u.get("item_name"),
                "citation": code,
                "episode_title": episode_title,
                "reason": u.get("reason"),
            })

        for a in result.get("possible_additions", []):
            part_info = part_urls.get(a.get("part", 1), part_urls.get(1))
            link = make_youtube_link(part_info["url"], a.get("timestamp_seconds"))
            additions.append({
                "citation": code,
                "episode_title": episode_title,
                "timestamp_seconds": a.get("timestamp_seconds"),
                "timestamp_display": fmt_timestamp(a["timestamp_seconds"]) if a.get("timestamp_seconds") is not None else None,
                "link": link,
                "subject": a.get("subject"),
                "suggested_header": a.get("suggested_header"),
                "confidence": a.get("confidence"),
                "note": a.get("note"),
            })

        print(f"  -> {len(result.get('verified', []))} verified, "
              f"{len(result.get('unverified', []))} unverified, "
              f"{len(result.get('possible_additions', []))} possible addition(s)")

        answered = len(result.get('verified', [])) + len(result.get('unverified', []))
        if answered < len(relevant_items):
            print(f"  !! WARNING: {len(relevant_items)} bullet(s) needed checking but only "
                  f"{answered} got an answer -- the model skipped some rather than answering "
                  f"every one. Consider re-running this episode alone once state is inspected "
                  f"(remove '{code}' from citation_check_state.json's 'done' list, then re-run).")

        done.add(code)
        state["done"] = sorted(done)
        save_state(state)
        save_json_list(CITATION_INDEX_FILE, citation_index)
        save_json_list(UNVERIFIED_FILE, unverified)
        save_json_list(ADDITIONS_FILE, additions)

    remaining = len(episodes) - len(done)
    print(f"\nDone with this batch. {len(done)} total processed, {remaining} remaining.")
    if remaining > 0:
        print(f"Re-run the same command to continue (next {args.limit}), "
              f"or add --limit {remaining} to finish everything left.")


if __name__ == "__main__":
    main()
