"""CLI tool specifically built for Grok Bot to push scraped mentions directly into ReplyInPublic."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import connect
from app.ingest import ingest_records, parse_raw_lines


def main():
    parser = argparse.ArgumentParser(description="Direct ingestion tool for Grok Bot.")
    parser.add_argument("--stdin", action="store_true", help="Read JSON or JSONL from stdin")
    parser.add_argument("--json", dest="json_str", help="JSON string or array of mentions")
    parser.add_argument("--file", dest="file_path", help="Path to JSON or JSONL file")
    parser.add_argument("--text", dest="text", help="Single mention text")
    parser.add_argument("--brand", dest="brand", default="instant", help="Brand name or ID")
    parser.add_argument("--author", dest="author", default="x_user", help="X author handle")
    parser.add_argument("--url", dest="url", default="", help="X post URL")
    parser.add_argument("--posted_at", dest="posted_at", default="", help="ISO timestamp")
    args = parser.parse_args()

    items = []

    # 1. From CLI individual flags
    if args.text:
        items.append({
            "brand_id": args.brand,
            "platform": "x",
            "author": args.author,
            "text": args.text,
            "url": args.url,
            "posted_at": args.posted_at,
            "brand_replied": False,
        })

    # 2. From JSON string
    elif args.json_str:
        raw = args.json_str.strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                items.extend(parsed)
            elif isinstance(parsed, dict):
                items.append(parsed)
        except Exception:
            items.extend(parse_raw_lines(raw))

    # 3. From file
    elif args.file_path:
        p = Path(args.file_path)
        if p.is_file():
            content = p.read_text(encoding="utf-8")
            try:
                parsed = json.loads(content)
                if isinstance(parsed, list):
                    items.extend(parsed)
                elif isinstance(parsed, dict):
                    items.append(parsed)
            except Exception:
                items.extend(parse_raw_lines(content))
        else:
            print(f"[ERROR] File not found: {p}", file=sys.stderr)
            sys.exit(1)

    # 4. From stdin
    elif args.stdin:
        content = sys.stdin.read().strip()
        if content:
            try:
                parsed = json.loads(content)
                if isinstance(parsed, list):
                    items.extend(parsed)
                elif isinstance(parsed, dict):
                    items.append(parsed)
            except Exception:
                items.extend(parse_raw_lines(content))

    if not items:
        print("[ERROR] No mentions provided to ingest. Provide --json, --file, or pipe via stdin.", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Ingesting {len(items)} mention(s) directly into Tiger Data...")
    with connect() as conn:
        res = ingest_records(conn, items)

    print(
        f"[SUCCESS] Ingest complete: {res['added']} added, "
        f"{res['duplicates']} duplicates skipped, {res['rejected']} rejected, "
        f"{res.get('gemini_labeled', 0)} categorized by Gemini."
    )


if __name__ == "__main__":
    main()
