"""Bulletproof ingestion engine for Grok and external social mentions.
Handles all edge cases: multi-platform, variable schemas, dirty formatting, null bytes, dedup.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.collect_social import insert_row
from app.segment import label_rules

BRAND_ALIASES = {
    # Instant
    "instant pot": "instant",
    "instantpot": "instant",
    "instant": "instant",
    "instant brands": "instant",
    # KitchenAid
    "kitchenaid": "kitchenaid",
    "kitchen aid": "kitchenaid",
    "kitchenaidusa": "kitchenaid",
    # Traeger
    "traeger": "traeger",
    "traeger grills": "traeger",
    "traegergrills": "traeger",
    # Ninja
    "ninja": "ninja",
    "ninjakitchen": "ninja",
    "sharkninja": "ninja",
    "shark ninja": "ninja",
    # De'Longhi
    "delonghi": "delonghi",
    "de'longhi": "delonghi",
    "de longhi": "delonghi",
    "dinamica": "delonghi",
    "magnifica": "delonghi",
    "specialista": "delonghi",
    "dedica": "delonghi",
    # Other known brands
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

    # Fallback to instant if unknown
    return "instant"


def detect_platform(raw_plat: str, url: str) -> str:
    p = (raw_plat or "").lower().strip()
    if p in {"youtube", "instagram", "tiktok", "x", "twitter", "reddit", "facebook", "amazon", "trustpilot", "threads", "bluesky", "bbb", "web"}:
        return "x" if p == "twitter" else p

    url_lower = (url or "").lower()
    if "twitter.com" in url_lower or "x.com" in url_lower:
        return "x"
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    if "instagram.com" in url_lower:
        return "instagram"
    if "tiktok.com" in url_lower:
        return "tiktok"
    if "reddit.com" in url_lower:
        return "reddit"
    if "amazon." in url_lower:
        return "amazon"
    if "trustpilot.com" in url_lower:
        return "trustpilot"
    if "threads.net" in url_lower:
        return "threads"
    if "bsky.app" in url_lower:
        return "bluesky"
    if "facebook.com" in url_lower:
        return "facebook"
    if "bbb.org" in url_lower:
        return "bbb"

    if url:
        try:
            domain = urlparse(url).netloc.lower()
            if domain:
                parts = domain.replace("www.", "").split(".")
                if parts and len(parts[0]) > 2:
                    return re.sub(r"[^a-z0-9]", "", parts[0])
        except Exception:
            pass

    return p or "web"


def parse_timestamp(raw_val) -> str:
    if not raw_val:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(raw_val, datetime):
        if raw_val.tzinfo is None:
            raw_val = raw_val.replace(tzinfo=timezone.utc)
        return raw_val.isoformat()
    if isinstance(raw_val, (int, float)):
        try:
            ts = float(raw_val)
            if ts > 1e11:  # milliseconds
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except Exception:
            return datetime.now(timezone.utc).isoformat()

    val_str = str(raw_val).strip()
    # Normalize common ISO string formats
    val_str = val_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(val_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception:
        pass

    # Try common date formats
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(val_str, fmt).replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            pass

    return datetime.now(timezone.utc).isoformat()


def extract_native_id(url: str, text: str, platform: str) -> str:
    if url:
        # Common status/post ID regex
        match = re.search(r"/(?:status|p|comments|reviews)/([0-9a-zA-Z_-]+)", url)
        if match:
            return match.group(1)[:40]
    # Fallback to hash
    return hashlib.sha256((url or text).encode("utf-8")).hexdigest()[:24]


def get_field(item: dict, *keys: str, default="") -> str:
    for k in keys:
        if k in item and item[k] is not None:
            return str(item[k]).strip()
    item_lower = {k.lower().replace("_", "").replace("-", ""): v for k, v in item.items() if v is not None}
    for k in keys:
        norm_k = k.lower().replace("_", "").replace("-", "")
        if norm_k in item_lower:
            return str(item_lower[norm_k]).strip()
    return default


def normalize_mention(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None

    # Text resolution across all known key variants (case-insensitive)
    text = get_field(item, "text", "comment", "content", "body", "message", "description", "post", "review", "complaint")
    # Strip null bytes (PostgreSQL fatal error) and control chars
    text = text.replace("\x00", "").strip()
    if not text:
        return None
    text = text[:8000]

    # URL resolution
    url = get_field(item, "url", "link", "permalink", "source_url", "uri", "web_url")

    # Platform resolution
    raw_plat = get_field(item, "platform", "site", "website", "source", "channel")
    platform = detect_platform(raw_plat, url)

    # Author resolution
    author = get_field(item, "author", "username", "user", "handle", "screen_name", "reviewer", default=f"{platform}_user")

    # Brand resolution
    raw_brand = get_field(item, "brand_id", "brand", "brandName", "company", "target", "product")
    brand_id = resolve_brand(raw_brand, text)

    # Timestamp
    raw_time = item.get("posted_at") or item.get("created_at") or item.get("timestamp") or item.get("date") or item.get("time") or item.get("published_at")
    if not raw_time:
        raw_time = get_field(item, "posted_at", "created_at", "timestamp", "date", "time", "published_at")
    posted_at = parse_timestamp(raw_time)

    # Native ID
    native_id = str(item.get("native_id") or item.get("id") or "").strip()
    if not native_id:
        native_id = extract_native_id(url, text, platform)

    if not url:
        url = f"https://{platform}.com/{author}/{native_id}"

    brand_replied = bool(item.get("brand_replied", False))
    reply_text = item.get("reply_text")
    parent_url = item.get("parent_url")
    surface = str(item.get("surface") or ("owned" if brand_replied else "earned")).lower().strip()
    proof = str(item.get("proof") or "bot_ingest")
    collected_by = str(item.get("collected_by") or platform or "bot")

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
    cleaned_raw = raw.strip()

    # Strip markdown backticks
    if cleaned_raw.startswith("```"):
        cleaned_raw = re.sub(r"^```[a-zA-Z]*\n", "", cleaned_raw)
        cleaned_raw = re.sub(r"\n```$", "", cleaned_raw).strip()

    # 1. Try parsing full content as JSON
    try:
        parsed = json.loads(cleaned_raw)
        if isinstance(parsed, list):
            return [x for x in parsed if isinstance(x, dict)]
        if isinstance(parsed, dict):
            if "items" in parsed and isinstance(parsed["items"], list):
                return [x for x in parsed["items"] if isinstance(x, dict)]
            return [parsed]
    except Exception:
        pass

    # 2. Try parsing full content as Python literal dict (single quotes)
    try:
        parsed = ast.literal_eval(cleaned_raw)
        if isinstance(parsed, list):
            return [x for x in parsed if isinstance(x, dict)]
        if isinstance(parsed, dict):
            return [parsed]
    except Exception:
        pass

    # 3. Line-by-line parsing
    for line in cleaned_raw.splitlines():
        line = line.strip()
        if not line or line.startswith("```"):
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                items.append(parsed)
            elif isinstance(parsed, list):
                items.extend([x for x in parsed if isinstance(x, dict)])
            continue
        except Exception:
            pass

        try:
            parsed = ast.literal_eval(line)
            if isinstance(parsed, dict):
                items.append(parsed)
                continue
        except Exception:
            pass

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

        # Fast URL deduplication check
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM mentions WHERE url = %s LIMIT 1;", (row["url"],))
            if cur.fetchone():
                duplicates += 1
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

    # Automatically run Gemini categorization on newly added mentions
    gemini_labeled = 0
    if added > 0:
        try:
            from app.segment import label_gemini
            gemini_labeled, _ = label_gemini(conn, limit_batches=max(1, (added + 29) // 30))
        except Exception:
            gemini_labeled = 0

    return {
        "status": "ok",
        "total_received": len(items),
        "added": added,
        "duplicates": duplicates,
        "rejected": rejected,
        "rule_labeled": labeled,
        "gemini_labeled": gemini_labeled,
    }
