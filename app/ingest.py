"""Ingestion helper for Grok and external social mentions."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from app.collect_social import insert_row
from app.segment import label_rules

BRAND_ALIASES = {
    "instant pot": "instant",
    "instantpot": "instant",
    "instant": "instant",
    "kitchenaid": "kitchenaid",
    "kitchen aid": "kitchenaid",
    "traeger": "traeger",
    "ninja": "ninja",
    "ninjakitchen": "ninja",
    "delonghi": "delonghi",
    "de'longhi": "delonghi",
    "de longhi": "delonghi",
    "nespresso": "nespresso",
    "breville": "breville",
    "vitamix": "vitamix",
    "la marzocco": "lamarzocco",
    "lamarzocco": "lamarzocco",
    "caraway": "caraway",
    "our place": "ourplace",
    "ourplace": "ourplace",
    "solo stove": "solostove",
    "solostove": "solostove",
    "made in": "madein",
    "madein": "madein",
    "lodge": "lodge",
    "meater": "meater",
    "fellow": "fellow",
    "anova": "anova",
}

VALID_BRANDS = set(BRAND_ALIASES.values())


def resolve_brand(brand_input: str, text: str) -> str:
    cleaned = (brand_input or "").lower().strip()
    if cleaned in BRAND_ALIASES:
        return BRAND_ALIASES[cleaned]
    if cleaned in VALID_BRANDS:
        return cleaned

    # Search in text for keywords
    text_lower = text.lower()
    for alias, bid in BRAND_ALIASES.items():
        if alias in text_lower:
            return bid
    return "instant"  # fallback default


def normalize_mention(item: dict) -> dict | None:
    text = str(item.get("text") or "").strip()
    if not text:
        return None

    brand_id = resolve_brand(str(item.get("brand_id") or item.get("brand") or ""), text)
    platform = str(item.get("platform") or "x").lower().strip()
    surface = str(item.get("surface") or "earned").lower().strip()
    author = str(item.get("author") or item.get("username") or "x_user").strip()

    posted_at_raw = item.get("posted_at")
    if posted_at_raw:
        if isinstance(posted_at_raw, datetime):
            posted_at = posted_at_raw.isoformat()
        else:
            posted_at = str(posted_at_raw).strip()
    else:
        posted_at = datetime.now(timezone.utc).isoformat()

    url = str(item.get("url") or "").strip()
    native_id = str(item.get("native_id") or item.get("id") or "").strip()

    if not native_id:
        # Check if URL contains tweet ID
        match = re.search(r"status/(\d+)", url)
        if match:
            native_id = match.group(1)
        else:
            native_id = hashlib.sha256((url or text).encode("utf-8")).hexdigest()[:24]

    if not url:
        url = f"https://x.com/{author}/status/{native_id}"

    brand_replied = bool(item.get("brand_replied", False))
    reply_text = item.get("reply_text")
    parent_url = item.get("parent_url")
    proof = str(item.get("proof") or "grok_bot")
    collected_by = str(item.get("collected_by") or "grok")

    return {
        "posted_at": posted_at,
        "brand_id": brand_id,
        "platform": platform,
        "surface": surface,
        "native_id": native_id,
        "url": url,
        "author": author,
        "text": text,
        "parent_url": parent_url,
        "brand_replied": brand_replied,
        "reply_text": reply_text,
        "proof": proof,
        "collected_by": collected_by,
    }


def parse_raw_lines(raw: str) -> list[dict]:
    items = []
    lines = raw.strip().splitlines()
    for line in lines:
        cleaned = line.strip()
        if not cleaned:
            continue
        if cleaned.startswith("```"):
            continue
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                items.append(parsed)
            elif isinstance(parsed, list):
                items.extend([x for x in parsed if isinstance(x, dict)])
        except Exception:
            continue
    return items


def ingest_records(conn, items: list[dict]) -> dict:
    added = 0
    duplicates = 0
    rejected = 0

    for item in items:
        row = normalize_mention(item)
        if not row:
            rejected += 1
            continue
        res = insert_row(conn, row)
        if res == "added":
            added += 1
        elif res == "old":
            duplicates += 1
        else:
            rejected += 1

    conn.commit()

    # Automatically run rule classification on newly ingested rows
    try:
        labeled = label_rules(conn)
    except Exception:
        labeled = 0

    return {
        "status": "ok",
        "total_received": len(items),
        "added": added,
        "duplicates": duplicates,
        "rejected": rejected,
        "rule_labeled": labeled,
    }
