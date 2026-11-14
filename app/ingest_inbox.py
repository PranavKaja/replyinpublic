"""CLI tool to ingest Grok / external JSON / JSONL files from inbox into Tiger Data."""

import argparse
import json
import sys
from pathlib import Path

from app.db import connect
from app.ingest import ingest_records, parse_raw_lines

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "inbox"


def main():
    parser = argparse.ArgumentParser(description="Ingest mentions from inbox into Tiger Data.")
    parser.add_argument("file", nargs="?", help="Specific JSON or JSONL file to ingest")
    args = parser.parse_args()

    files = []
    if args.file:
        p = Path(args.file)
        if not p.is_file():
            print(f"File not found: {p}")
            sys.exit(1)
        files.append(p)
    elif INBOX.exists():
        files.extend(sorted(INBOX.glob("*.jsonl")))
        files.extend(sorted(INBOX.glob("*.json")))

    if not files:
        print(f"No files found in {INBOX}. Drop a .jsonl file there or pass a file path.")
        return

    with connect() as conn:
        for file_path in files:
            print(f"[*] Processing {file_path.name}...")
            content = file_path.read_text(encoding="utf-8")
            items = []
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    items = [data]
            except Exception:
                items = parse_raw_lines(content)

            if not items:
                print(f"[-] No valid records found in {file_path.name}")
                continue

            res = ingest_records(conn, items)
            print(
                f"[+] Done: {res['added']} added, {res['duplicates']} duplicates, "
                f"{res['rejected']} rejected, {res['rule_labeled']} rule-labeled."
            )


if __name__ == "__main__":
    main()
