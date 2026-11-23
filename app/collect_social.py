"""Pull Instagram, TikTok, X, and Reddit for the five focus brands.

Each actor run has a dollar cap. A failed source is recorded and the others continue.
Rows without a URL, text, or publish time are rejected.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.db import ROOT, connect, load_env
from app.hooks import stamp_case_id
from app.segment import ensure_labels, is_noise, save_label

FOCUS_PATH = ROOT / "focus.json"
CAPS = {
    "instagram": Decimal("0.20"),
    "tiktok": Decimal("0.50"),
    "x": Decimal("0.40"),
    "reddit": Decimal("0.40"),
}


def load_focus(conn) -> list[dict]:
    wanted = json.loads(FOCUS_PATH.read_text(encoding="utf-8"))["brands"]
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, instagram_handle, search_terms, own_handles
            FROM brands
            WHERE id = ANY(%s)
            """,
            (wanted,),
        )
        rows = {
            brand_id: {
                "id": brand_id,
                "name": name,
                "instagram_handle": handle,
                "search_terms": terms or [],
                "own_handles": handles or [],
            }
            for brand_id, name, handle, terms, handles in cur.fetchall()
        }
    return [rows[brand_id] for brand_id in wanted if brand_id in rows]


def main() -> None:
    load_env()
    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token:
        raise SystemExit("APIFY_TOKEN is missing from .env")
    from apify_client import ApifyClient

    client = ApifyClient(token)
    only = {arg for arg in sys.argv[1:] if not arg.startswith("-")}
    with connect() as conn:
        ensure_labels(conn)
        brands = load_focus(conn)
        print("focus " + ", ".join(brand["name"] for brand in brands), flush=True)
        steps = (
            ("instagram", instagram),
            ("tiktok", tiktok),
            ("x", tweets),
            ("reddit", reddit),
        )
        for name, func in steps:
            if only and name not in only:
                continue
            func(client, conn, brands)


def run_actor(client, actor: str, payload: dict, source: str) -> list[dict]:
    result = client.actor(actor).call(
        run_input=payload,
        max_total_charge_usd=CAPS[source],
        logger=None,
    )
    if result is None:
        raise RuntimeError(f"{actor} did not finish")
    dataset = result.get("defaultDatasetId") if isinstance(result, dict) else result.default_dataset_id
    return list(client.dataset(dataset).iterate_items())


def start_run(conn, source: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO runs (source, started_at) VALUES (%s, now()) RETURNING id",
            (source,),
        )
        run_id = cur.fetchone()[0]
    conn.commit()
    return run_id


def finish_run(conn, run_id: int, added: int, rejected: int, error: str | None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE runs
            SET finished_at = now(), added = %s, rejected = %s, units = 0, error = %s
            WHERE id = %s
            """,
            (added, rejected, error, run_id),
        )
    conn.commit()


def insert_row(conn, row: dict) -> str:
    if not row.get("url") or not str(row.get("text") or "").strip() or not row.get("posted_at"):
        return "reject"
    if not str(row.get("native_id") or "").strip():
        import hashlib
        row["native_id"] = hashlib.sha256((row.get("url") or row.get("text", "")).encode("utf-8")).hexdigest()[:24]
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO mentions (
              posted_at, brand_id, platform, surface, native_id, url, author, text,
              parent_url, brand_replied, reply_text, proof, collected_by
            ) VALUES (
              %(posted_at)s, %(brand_id)s, %(platform)s, %(surface)s, %(native_id)s,
              %(url)s, %(author)s, %(text)s, %(parent_url)s, %(brand_replied)s,
              %(reply_text)s, %(proof)s, %(collected_by)s
            )
            ON CONFLICT (platform, native_id, posted_at) DO NOTHING
            RETURNING id, posted_at
            """,
            row,
        )
        saved = cur.fetchone()
        if not saved:
            return "old"
        stamp_case_id(cur, saved[0], row["brand_id"])
    if is_noise(row["text"]):
        save_label(conn, saved[0], saved[1], {
            "type": "noise",
            "sentiment": "neutral",
            "urgency": "low",
            "is_buyer": False,
            "relevant": False,
            "model": "rules",
            "topic": None,
        })
    return "added"


def instagram(client, conn, brands: list[dict]) -> None:
    run_id = start_run(conn, "instagram")
    added = rejected = 0
    notes = []
    since = (datetime.now(timezone.utc) - timedelta(days=14)).date().isoformat()
    for brand in brands:
        handle = (brand["instagram_handle"] or "").lstrip("@")
        if not handle:
            notes.append(f"{brand['name']}: no instagram handle")
            continue
        try:
            posts = run_actor(client, "apify/instagram-scraper", {
                "directUrls": [f"https://www.instagram.com/{handle}/"],
                "resultsType": "posts",
                "resultsLimit": 2,
                "onlyPostsNewerThan": since,
            }, "instagram")
            urls = [post.get("url") for post in posts if post.get("url") and not post.get("error")]
            comments = []
            if urls:
                comments = run_actor(client, "apify/instagram-scraper", {
                    "directUrls": urls,
                    "resultsType": "comments",
                    "resultsLimit": 15,
                }, "instagram")
        except Exception as exc:
            notes.append(f"{brand['name']}: {exc.__class__.__name__}: {exc}")
            continue
        own = {handle.lower(), *(h.lower().lstrip("@") for h in brand["own_handles"])}
        for comment in comments:
            if comment.get("error"):
                continue
            author = (comment.get("ownerUsername") or "").lstrip("@")
            if author.lower() in own:
                continue
            replies = comment.get("replies") or []
            reply = next((item for item in replies if (item.get("ownerUsername") or "").lower() in own), None)
            kind = insert_row(conn, {
                "posted_at": parse_time(comment.get("timestamp")),
                "brand_id": brand["id"],
                "platform": "instagram",
                "surface": "own",
                "native_id": str(comment.get("id") or ""),
                "url": comment.get("commentUrl") or comment.get("url") or "",
                "author": author or None,
                "text": (comment.get("text") or "").strip(),
                "parent_url": comment.get("postUrl") or "",
                "brand_replied": True if reply else None,
                "reply_text": (reply or {}).get("text"),
                "proof": "api" if reply else "none",
                "collected_by": "apify",
            })
            if kind == "added":
                added += 1
            elif kind == "reject":
                rejected += 1
        conn.commit()
        print(f"instagram {brand['name']}: running added {added}", flush=True)
    finish_run(conn, run_id, added, rejected, "; ".join(notes)[:2000] or None)
    print(f"instagram added {added} rejected {rejected}", flush=True)


def tiktok(client, conn, brands: list[dict]) -> None:
    run_id = start_run(conn, "tiktok")
    handles = [brand["instagram_handle"].lstrip("@") for brand in brands if brand["instagram_handle"]]
    by_handle = {brand["instagram_handle"].lower().lstrip("@"): brand for brand in brands}
    added = rejected = 0
    error = None
    try:
        items = run_actor(client, "clockworks/tiktok-scraper", {
            "profiles": handles,
            "resultsPerPage": 2,
            "commentsPerPost": 15,
            "topLevelCommentsPerPost": 15,
            "maxRepliesPerComment": 3,
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
            "shouldDownloadSlideshowImages": False,
            "shouldDownloadAvatars": False,
            "shouldDownloadMusicCovers": False,
        }, "tiktok")
    except Exception as exc:
        items = []
        error = f"{exc.__class__.__name__}: {exc}"
    if items:
        print("tiktok item keys " + ", ".join(sorted(items[0].keys())[:8]), flush=True)
    for item in items:
        comments = item.get("comments") or []
        if not comments and item.get("commentsDatasetUrl"):
            comments = dataset_items(client, item["commentsDatasetUrl"])
        profile = (item.get("authorMeta") or {})
        blob = " ".join(str(profile.get(key) or "") for key in ("name", "uniqueId", "nickName"))
        video_url = str(item.get("webVideoUrl") or item.get("url") or "")
        brand = None
        for handle, candidate in by_handle.items():
            if handle and (handle in blob.lower() or f"@{handle}" in video_url.lower()):
                brand = candidate
                break
        if not brand or not comments:
            continue
        if comments:
            print("tiktok comment keys " + ", ".join(sorted(comments[0].keys())[:8]), flush=True)
        for comment in comments:
            kind = insert_row(conn, tiktok_comment(brand, item, comment))
            added, rejected = tally(kind, added, rejected)
    conn.commit()
    finish_run(conn, run_id, added, rejected, error)
    print(f"tiktok added {added} rejected {rejected} error {error}", flush=True)


def dataset_items(client, url: str) -> list[dict]:
    marker = "/datasets/"
    if marker not in url:
        return []
    dataset_id = url.split(marker, 1)[1].split("/")[0].split("?")[0]
    return list(client.dataset(dataset_id).iterate_items())


def tiktok_comment(brand: dict, video: dict, comment: dict) -> dict:
    author = comment.get("uniqueId") or comment.get("user") or ""
    handle = brand["instagram_handle"].lower().lstrip("@")
    replied = str(author).lower().lstrip("@") == handle
    return {
        "posted_at": parse_time(comment.get("createTimeISO") or comment.get("createTime")),
        "brand_id": brand["id"],
        "platform": "tiktok",
        "surface": "own",
        "native_id": str(comment.get("cid") or comment.get("commentId") or comment.get("id") or ""),
        "url": comment.get("commentUrl") or video.get("webVideoUrl") or video.get("url") or "",
        "author": str(author).lstrip("@") or None,
        "text": (comment.get("text") or "").strip(),
        "parent_url": video.get("webVideoUrl") or video.get("url") or "",
        "brand_replied": True if replied else None,
        "reply_text": None,
        "proof": "none",
        "collected_by": "apify",
    }


def tweets(client, conn, brands: list[dict]) -> None:
    run_id = start_run(conn, "x")
    terms = []
    for brand in brands:
        terms.extend(brand["search_terms"] or [brand["name"]])
    added = rejected = 0
    error = None
    try:
        items = run_actor(client, "apidojo/tweet-scraper", {
            "searchTerms": terms,
            "maxItems": 30,
            "sort": "Latest",
            "start": (datetime.now(timezone.utc) - timedelta(days=14)).date().isoformat(),
        }, "x")
    except Exception as exc:
        items = []
        error = f"{exc.__class__.__name__}: {exc}"
    if items:
        print("x item keys " + ", ".join(sorted(items[0].keys())[:12]), flush=True)
    for item in items:
        text = item.get("fullText") or item.get("text") or ""
        brand = match_brand(text, brands)
        if not brand:
            continue
        author_obj = item.get("author") if isinstance(item.get("author"), dict) else {}
        author = author_obj.get("userName") or item.get("userName") or ""
        author = str(author).lstrip("@")
        tweet_id = str(item.get("id") or "")
        url = item.get("url") or item.get("twitterUrl") or ""
        if not url and author and tweet_id:
            url = f"https://x.com/{author}/status/{tweet_id}"
        kind = insert_row(conn, {
            "posted_at": parse_time(item.get("createdAt") or item.get("created_at")),
            "brand_id": brand["id"],
            "platform": "x",
            "surface": "other",
            "native_id": tweet_id,
            "url": url,
            "author": author or None,
            "text": text.strip(),
            "parent_url": url,
            "brand_replied": None,
            "reply_text": None,
            "proof": "none",
            "collected_by": "apify",
        })
        added, rejected = tally(kind, added, rejected)
    conn.commit()
    finish_run(conn, run_id, added, rejected, error)
    print(f"x added {added} rejected {rejected} error {error}", flush=True)


def reddit(client, conn, brands: list[dict]) -> None:
    run_id = start_run(conn, "reddit")
    terms = []
    for brand in brands:
        terms.extend(brand["search_terms"][:1] or [brand["name"]])
    added = rejected = 0
    error = None
    try:
        items = run_actor(client, "trudax/reddit-scraper", {
            "searches": terms,
            "searchPosts": True,
            "searchComments": True,
            "sort": "new",
            "time": "week",
            "maxItems": 40,
            "maxComments": 10,
            "maxPostCount": 10,
            "includeNSFW": False,
            "skipUserPosts": False,
        }, "reddit")
    except Exception as exc:
        items = []
        error = f"{exc.__class__.__name__}: {exc}"
    if items:
        print("reddit item keys " + ", ".join(sorted(items[0].keys())[:12]), flush=True)
    else:
        print("reddit items 0", flush=True)
    for item in items:
        text = item.get("body") or item.get("text") or item.get("title") or ""
        brand = match_brand(text, brands)
        if not brand:
            continue
        kind = insert_row(conn, {
            "posted_at": parse_time(item.get("createdAt") or item.get("created")),
            "brand_id": brand["id"],
            "platform": "reddit",
            "surface": "other",
            "native_id": str(item.get("id") or item.get("parsedId") or ""),
            "url": item.get("url") or item.get("link") or "",
            "author": str(item.get("username") or item.get("author") or "").lstrip("u/") or None,
            "text": text.strip(),
            "parent_url": item.get("postUrl") or item.get("url") or "",
            "brand_replied": None,
            "reply_text": None,
            "proof": "none",
            "collected_by": "apify",
        })
        added, rejected = tally(kind, added, rejected)
    conn.commit()
    finish_run(conn, run_id, added, rejected, error)
    print(f"reddit added {added} rejected {rejected} error {error}", flush=True)


def match_brand(text: str, brands: list[dict]) -> dict | None:
    folded = text.lower()
    for brand in brands:
        for term in brand["search_terms"] or [brand["name"]]:
            if term and term.lower() in folded:
                return brand
    return None


def parse_time(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        number = float(value)
        if number > 10_000_000_000:
            number = number / 1000
        return datetime.fromtimestamp(number, timezone.utc)
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    try:
        return datetime.strptime(str(value), "%a %b %d %H:%M:%S %z %Y")
    except ValueError:
        return None


def tally(kind: str, added: int, rejected: int) -> tuple[int, int]:
    if kind == "added":
        return added + 1, rejected
    if kind == "reject":
        return added, rejected + 1
    return added, rejected


if __name__ == "__main__":
    main()
