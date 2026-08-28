"""
Cafe Rise / Cornucopias — Per-Episode Feature Extraction (TEST RUN, Episodes 1-58)

What this does:
  1. Scans TRANSCRIPT_DIR for "Cafe Rise Episode N.json" files (merging
     "part 1"/"part 2" files into a single episode where present).
  2. For each episode in range EPISODE_MIN-EPISODE_MAX, sends the transcript
     text to the Anthropic API and asks it to extract features/development
     items using the SAME category taxonomy as your existing doc.
  3. Saves one raw JSON checkpoint per episode (so a crash/quota-out never
     loses prior work — just rerun and already-done episodes are skipped).
  4. Aggregates all checkpoints into one markdown file, grouped by category,
     for you to compare against the existing doc by hand.

Setup (one time):
    pip install anthropic

Before running (each terminal session):
    set ANTHROPIC_API_KEY=your_key_here

Run:
    python extract_features.py
"""

import os
import re
import json
import time
import sys

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

TRANSCRIPT_DIR = r"C:\Users\19782\Desktop\Rise-Underground.github.io\transcripts\Cafe_Rise"
CHECKPOINT_DIR = r"C:\Users\19782\Desktop\Rise Ledger\NFT_Data\feature_extraction_checkpoints"
OUTPUT_FILE = r"C:\Users\19782\Desktop\Rise Ledger\NFT_Data\feature_extraction_1-58.md"

EPISODE_MIN = 1
EPISODE_MAX = 58

MODEL = "claude-sonnet-5"
MAX_OUTPUT_TOKENS = 8192
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5

# Required only if your API key is an "identity-linked" key tied to a workspace.
# Leave as "" if you're not sure yet; the script will tell you if it's needed.
WORKSPACE_ID = ""

# Taxonomy pulled directly from Cornucopious_Features_In_Development_Updated_42.docx
CATEGORIES = {
    "Team & Hiring": [],
    "World & Exploration": ["New World Zones", "Map & Navigation", "Travel & Transport"],
    "Gameplay & Core Loops": [
        "Mining & Ore Processing", "Fishing", "Farming", "Crafting",
        "Questing", "Combat & Rifts", "Vehicles", "Mini Experiences / Game Loops",
    ],
    "Animals & Creatures": [],
    "Building & Property": ["Apartment Builder", "Land Building", "Custom Domes"],
    "Social & Multiplayer": [],
    "Racing & Esports": [],
    "Economy & Progression": [
        "In-Game Currency (IGC)", "Play to Earn / Build to Earn",
        "NFT Staking", "Marketplace", "Wallets", "Governance",
    ],
    "Avatars & Customisation": [],
    "AI & NPCs": [],
    "Platforms & Additional Products": [
        "UI & Menus", "Mobile Game", "Epic Games Store & Steam",
        "Copious Academy", "Copi Watch / Companion App", "Merchandise Shop",
    ],
    "Seasonal Content & Events": [],
    "Nodes & Infrastructure": [],
    "Lore & Story": [],
    "Partnerships & Advisers": [
        "Game & Economy Advisers", "NFT & Tech Partners",
        "Content & Community Partners", "Events & Conferences",
    ],
    "R&D & Future Technology": [],
}

STATUS_OPTIONS = ["Complete", "WIP", "Partial Completion", "Cancelled/Scrapped"]

FILENAME_RE = re.compile(
    r"Cafe[\s_]+Rise[\s_]+Episode[\s_]+(\d+)(?:[\s_]+part[\s_]+(\d+))?\.json",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# STEP 1 — Load and group episode files
# ---------------------------------------------------------------------------

def load_episode_groups(transcript_dir):
    """Returns {episode_num: [ (part_num or 0, filepath), ... ]} sorted by part."""
    groups = {}
    if not os.path.isdir(transcript_dir):
        print(f"ERROR: transcript directory not found: {transcript_dir}")
        sys.exit(1)

    for fname in os.listdir(transcript_dir):
        m = FILENAME_RE.match(fname)
        if not m:
            continue
        ep_num = int(m.group(1))
        part_num = int(m.group(2)) if m.group(2) else 0
        groups.setdefault(ep_num, []).append((part_num, os.path.join(transcript_dir, fname)))

    for ep_num in groups:
        groups[ep_num].sort(key=lambda x: x[0])

    return groups


def build_episode_record(ep_num, part_files):
    """Merge part files (if any) into a single episode record."""
    title = None
    upload_date = None
    url = None
    text_chunks = []

    for _, filepath in part_files:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if title is None:
            title = data.get("title")
            upload_date = data.get("upload_date")
            url = data.get("url")
        text_chunks.append(data.get("transcript_text") or "")

    return {
        "episode": ep_num,
        "title": title,
        "upload_date": upload_date,
        "url": url,
        "transcript_text": "\n\n".join(text_chunks),
    }


# ---------------------------------------------------------------------------
# STEP 2 — Build prompt and call the API
# ---------------------------------------------------------------------------

def build_taxonomy_block():
    lines = []
    for cat, subs in CATEGORIES.items():
        if subs:
            lines.append(f"- {cat}: {', '.join(subs)}")
        else:
            lines.append(f"- {cat}")
    return "\n".join(lines)


def build_prompt(episode_record):
    taxonomy_block = build_taxonomy_block()
    status_block = ", ".join(STATUS_OPTIONS)

    return f"""You are extracting development/feature information from a single episode
transcript of the Cafe Rise / Copi Cafe podcast (Cornucopias / Infinity Rising project).

Episode: {episode_record['episode']}
Title: {episode_record['title']}
Upload date: {episode_record['upload_date']}

The transcript below is raw auto-generated captions: no punctuation, occasional
misheard words (e.g. "Cornucopious" may appear as "cornucopias", "copic", etc;
"Cardano" may appear as "cardono"). Read through this and interpret it correctly.

TASK: Extract every distinct feature, system, product, or piece of content that
the hosts describe as something they ARE actively doing, building, or working
on right now — committed, in-progress, or completed work.

STRICT FILTER — this is the most important rule: only include something if it's
phrased with commitment/certainty ("we are building X", "we're working on Y",
"we've added Z", "this is done", "we are doing this"). DO NOT include anything
phrased as speculation, brainstorming, or a hypothetical ("we could do X",
"maybe we'll add Y", "what if we tried Z", "we might explore", "it would be
cool if", "we're kicking around the idea of"). If a host is just throwing out
an idea or thinking out loud rather than describing real, committed work,
leave it out entirely — do not include it even with a "teased" or "idea"
status. When in doubt about whether something is committed or speculative,
leave it out.

For each item that passes the filter, classify it into the SAME category
taxonomy below (use the closest match; if genuinely nothing fits, use
category "Uncategorized").

CATEGORY TAXONOMY (category: subcategories):
{taxonomy_block}

For each item found, output an object with these fields:
- "category": one of the main categories above
- "subcategory": a subcategory from that category's list, or null if none fits
- "item_name": short name for the feature/item
- "description": 1-2 sentences (keep it tight — under 300 characters) summarizing
  what was said about it in THIS episode (status, details, any dates/timelines
  mentioned). Write it as plain prose with no line breaks.
- "status": one of [{status_block}] based on what THIS episode implies
- "delivery_date_mentioned": any specific date/timeframe mentioned for delivery,
  or null if none was given

Only extract things actually discussed in this transcript. Do not invent items.
If the same feature is mentioned multiple times in this episode, merge it into
one entry with the fullest description.

Respond with ONLY a JSON array of these objects, nothing else. No markdown
fences, no preamble. If nothing relevant is found, respond with [].

TRANSCRIPT:
{episode_record['transcript_text']}
"""


def parse_model_json(text):
    """Parse the model's JSON array, salvaging complete items if the response
    was cut off mid-array (truncated) rather than discarding it entirely."""
    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError:
        pass

    # Truncated response: trim back to the last fully-closed object and
    # close the array there. Salvages whatever came through intact.
    idx = text.rfind("},")
    if idx != -1:
        repaired = text[: idx + 1] + "]"
        try:
            return json.loads(repaired, strict=False)
        except json.JSONDecodeError:
            pass

    idx = text.rfind("}")
    if idx != -1:
        repaired = text[: idx + 1] + "]"
        try:
            return json.loads(repaired, strict=False)
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("Could not parse or repair JSON", text, 0)


def call_model(client, prompt):
    from anthropic import APIStatusError, APIConnectionError

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_OUTPUT_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(
                block.text for block in response.content if block.type == "text"
            )
            text = text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(json)?", "", text).rstrip("`").strip()
            items = parse_model_json(text)
            if response.stop_reason == "max_tokens":
                print(f"    warning: response was truncated (hit token limit) — salvaged {len(items)} items, some may be missing")
            return items
        except (APIStatusError, APIConnectionError, json.JSONDecodeError) as e:
            last_error = e
            print(f"    attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS)
    raise RuntimeError(f"Failed after {MAX_RETRIES} attempts: {last_error}")


# ---------------------------------------------------------------------------
# STEP 3 — Main extraction loop (checkpointed / resumable)
# ---------------------------------------------------------------------------

def run_extraction():
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable is not set.")
        print('Set it with:  set ANTHROPIC_API_KEY=your_key_here')
        sys.exit(1)

    extra_headers = {"anthropic-workspace-id": WORKSPACE_ID} if WORKSPACE_ID else {}
    client = anthropic.Anthropic(api_key=api_key, default_headers=extra_headers)

    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    groups = load_episode_groups(TRANSCRIPT_DIR)

    episodes_to_run = [e for e in sorted(groups) if EPISODE_MIN <= e <= EPISODE_MAX]
    print(f"Found {len(episodes_to_run)} episodes in range {EPISODE_MIN}-{EPISODE_MAX}")

    for ep_num in episodes_to_run:
        checkpoint_path = os.path.join(CHECKPOINT_DIR, f"episode_{ep_num}.json")
        if os.path.exists(checkpoint_path):
            print(f"Episode {ep_num}: checkpoint exists, skipping")
            continue

        print(f"Episode {ep_num}: processing...")
        record = build_episode_record(ep_num, groups[ep_num])

        if not record["transcript_text"].strip():
            print(f"Episode {ep_num}: no transcript text, skipping")
            continue

        prompt = build_prompt(record)

        try:
            items = call_model(client, prompt)
        except RuntimeError as e:
            print(f"Episode {ep_num}: FAILED, aborting run. Nothing written for this episode.")
            print(f"  Error: {e}")
            print(f"Rerun the script to resume from episode {ep_num} once resolved.")
            sys.exit(1)

        checkpoint_data = {
            "episode": ep_num,
            "title": record["title"],
            "upload_date": record["upload_date"],
            "url": record["url"],
            "items": items,
        }
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(checkpoint_data, f, indent=2)

        print(f"Episode {ep_num}: extracted {len(items)} items")

    print("Extraction pass complete.")


# ---------------------------------------------------------------------------
# STEP 4 — Aggregate checkpoints into one comparison-friendly markdown file
# ---------------------------------------------------------------------------

def aggregate_output():
    if not os.path.isdir(CHECKPOINT_DIR):
        print(f"ERROR: checkpoint directory not found: {CHECKPOINT_DIR}")
        sys.exit(1)

    by_category = {cat: [] for cat in CATEGORIES}
    by_category["Uncategorized"] = []

    for fname in sorted(os.listdir(CHECKPOINT_DIR)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(CHECKPOINT_DIR, fname), "r", encoding="utf-8") as f:
            data = json.load(f)

        ep_num = data["episode"]
        for item in data.get("items", []):
            if not isinstance(item, dict):
                print(f"  warning: episode {ep_num} has a malformed item (not an object), skipping it: {item}")
                continue
            cat = item.get("category") if item.get("category") in by_category else "Uncategorized"
            item["_episode"] = ep_num
            by_category[cat].append(item)

    lines = ["# Feature Extraction — Test Run (Episodes 1-58)", ""]
    for cat, subs in list(CATEGORIES.items()) + [("Uncategorized", [])]:
        items = by_category.get(cat, [])
        if not items:
            continue
        lines.append(f"## {cat}")
        lines.append("")
        for item in items:
            sub = f" ({item.get('subcategory')})" if item.get("subcategory") else ""
            date_note = f" — mentioned date: {item['delivery_date_mentioned']}" if item.get("delivery_date_mentioned") else ""
            lines.append(
                f"- **{item.get('item_name')}**{sub} — {item.get('description')}"
                f"{date_note} (Episode {item['_episode']})({item.get('status')})"
            )
        lines.append("")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    total_items = sum(len(v) for v in by_category.values())
    print(f"Wrote {total_items} items to {OUTPUT_FILE}")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_extraction()
    aggregate_output()
