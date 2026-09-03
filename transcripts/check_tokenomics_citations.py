#!/usr/bin/env python3
"""
check_tokenomics_citations.py

Separate, one-time pass (not part of the per-episode batch loop, since
this checks against a PDF by section/page, not a timestamped video).
Verifies every "(T-Doc)" citation in the doc against the actual RISE
Tokenomics PDF -- 30 bullets as of the current doc.

Requires: pip install anthropic pypdf

Usage:
    python check_tokenomics_citations.py
"""

import json
import re
from pathlib import Path

import anthropic
from pypdf import PdfReader

TOKENOMICS_PDF = Path(r"C:\Users\19782\Desktop\Rise-Underground.github.io\transcripts\Docs\Infinity-Rising-Tokenomics-Paper.pdf")
ARCHIVE_DATA_FILE = Path("archive_data.json")
OUT_FILE = Path("tokenomics_citation_check.json")

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 4096

CITATION_RE = re.compile(r'\bT-Doc\b')

SYSTEM_PROMPT = """You are checking a community-maintained feature-tracking \
document's "(T-Doc)" citations against the actual RISE Tokenomics PDF they're \
supposed to reference.

For each bullet below, decide whether the tokenomics document actually \
supports/discusses that claim. Bullets were manually consolidated, so judge \
the SPIRIT of the match, not exact wording. If supported, give the page \
number and a short quote or paraphrase of the supporting text. If not \
supported (or you can't find it), say so plainly.

Respond with ONLY a single JSON object, no prose before or after:

{
  "verified": [
    {"header": "...", "item_name": "...", "page": 7, "note": "short justification"}
  ],
  "unverified": [
    {"header": "...", "item_name": "...", "reason": "short reason you could not confirm this"}
  ]
}
"""


def load_tdoc_items():
    data = json.loads(ARCHIVE_DATA_FILE.read_text(encoding="utf-8"))
    items = []
    for cat in data:
        header = cat["label"]
        for item in cat.get("items", []):
            desc = item.get("desc") or ""
            if CITATION_RE.search(desc):
                items.append({"header": header, "name": item.get("name"), "desc": desc})
    return items


def extract_pdf_text(pdf_path):
    reader = PdfReader(str(pdf_path))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(f"=== PAGE {i} ===\n{text}")
    return "\n\n".join(pages)


def parse_json_response(raw_text):
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in response")
    return json.loads(raw_text[start:end + 1])


def main():
    if not TOKENOMICS_PDF.exists():
        print(f"ERROR: tokenomics PDF not found at {TOKENOMICS_PDF} -- edit the path at the top of this script.")
        return
    if not ARCHIVE_DATA_FILE.exists():
        print(f"ERROR: {ARCHIVE_DATA_FILE} not found -- must sit next to this script.")
        return

    items = load_tdoc_items()
    print(f"Found {len(items)} bullet(s) citing (T-Doc).")
    if not items:
        print("Nothing to check.")
        return

    pdf_text = extract_pdf_text(TOKENOMICS_PDF)
    print(f"Extracted {len(pdf_text):,} characters from the tokenomics PDF.")

    items_block = "\n\n".join(
        f"- HEADER: {it['header']}\n  NAME: {it['name']}\n  DESC: {it['desc']}"
        for it in items
    )

    client = anthropic.Anthropic()
    print("Calling Claude...")
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"BULLETS TO CHECK:\n{items_block}\n\n"
                f"TOKENOMICS PDF TEXT:\n{pdf_text}"
            ),
        }],
    )
    raw = response.content[0].text
    result = parse_json_response(raw)

    print(f"Verified: {len(result.get('verified', []))}  "
          f"Unverified: {len(result.get('unverified', []))}")

    OUT_FILE.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
