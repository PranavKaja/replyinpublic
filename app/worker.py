"""One YouTube pass: discover videos at most twice a day, then refresh comments.

Search is not part of the 30 minute comment refresh. Video ids are stored in `videos`.
commentThreads.list is 1 unit per page. A thread with more than 5 replies is paged
with comments.list so a brand reply is not left in the unread tail.
"""

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.db import ROOT, connect, load_env
from app.youtube import CommentsDisabled, QuotaExceeded, YouTube, YouTubeError

EASTERN = ZoneInfo("America/New_York")
SEARCH_PASSES_PER_DAY = 2
OTHER_VIDEO_COUNT = 4
OWN_VIDEO_COUNT = 5
OTHER_LOOKBACK_DAYS = 30
SEARCH_RESULTS = 15
THREAD_PAGES = 2
COMMENT_REFRESH = timedelta(minutes=30)
REPLY_PAGE_CAP = 50
WORKERS = 6
_db_lock = threading.Lock()

REQUIRED_FIELDS = ("youtube_channel_id", "instagram_handle", "own_handles", "search_terms")


def main() -> None:
    load_env()
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not key:
        raise SystemExit("YOUTUBE_API_KEY is missing from .env")
    from app.schema import apply

    apply()
    brands = load_brands()
    yt = YouTube(key)
    added = 0
    rejected = 0
    reject_reasons: dict[str, int] = {}
    truncated = 0
    notes: list[str] = []
    quota_hit = False
    run_id = None
    conn = connect()
    conn.autocommit = False
    try:
        upsert_brands(conn, brands)
        run_id = start_run(conn)
        conn.commit()
        for brand in brands:
            if yt.stop:
                quota_hit = True
                break
            try:
                stats = process_brand(conn, yt, brand)
            except QuotaExceeded as exc:
                quota_hit = True
                notes.append(f"quota exceeded during {brand['name']}: {exc}")
                break
            except YouTubeError as exc:
                notes.append(f"{brand['name']}: {exc}")
                conn.rollback()
                continue
            added += stats["added"]
            rejected += stats["rejected"]
            truncated += stats["truncated"]
            for reason, count in stats["reasons"].items():
                reject_reasons[reason] = reject_reasons.get(reason, 0) + count
            print(
                f"{brand['name']}: own {stats['own']} | other {stats['other']} | "
                f"search {'yes' if stats['searched'] else 'skipped'} | "
                f"added {stats['added']} | rejected {stats['rejected']} | units {yt.units}"
            )
        error = None
        if quota_hit:
            error = "quota exceeded"
        elif notes:
            error = "; ".join(notes)[:2000]
        finish_run(conn, run_id, added, rejected, yt.units, error)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        if run_id is not None:
            finish_run(conn, run_id, added, rejected, yt.units, f"{exc.__class__.__name__}: {exc}"[:2000])
            conn.commit()
        raise
    finally:
        yt.close()
        try:
            report(conn, yt, added, rejected, reject_reasons, truncated, notes)
        finally:
            conn.close()
    if quota_hit:
        raise SystemExit(1)


def load_brands() -> list[dict]:
    payload = json.loads((ROOT / "brands.json").read_text(encoding="utf-8"))
    brands = payload["brands"]
    if len(brands) != 17:
        raise SystemExit(f"expected 17 brands, found {len(brands)}")
    seen = set()
    for brand in brands:
        brand_id = brand.get("brand_id")
        if not brand_id or brand_id in seen:
            raise SystemExit(f"bad brand id: {brand_id}")
        seen.add(brand_id)
        for field in REQUIRED_FIELDS:
            if field not in brand:
                raise SystemExit(f"{brand_id} is missing {field}")
        channel = brand["youtube_channel_id"]
        if not isinstance(channel, str) or not channel.startswith("UC"):
            raise SystemExit(f"{brand_id} has no YouTube channel id")
    return brands


def upsert_brands(conn, brands: list[dict]) -> None:
    with conn.cursor() as cur:
        for brand in brands:
            cur.execute(
                """
                INSERT INTO brands (
                  id, name, youtube_channel_id, instagram_handle, own_handles, search_terms
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                  name = EXCLUDED.name,
                  youtube_channel_id = EXCLUDED.youtube_channel_id,
                  instagram_handle = EXCLUDED.instagram_handle,
                  own_handles = EXCLUDED.own_handles,
                  search_terms = EXCLUDED.search_terms
                """,
                (
                    brand["brand_id"],
                    brand["name"],
                    brand["youtube_channel_id"],
                    brand["instagram_handle"],
                    brand["own_handles"],
                    brand["search_terms"],
                ),
            )


def start_run(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO runs (source, started_at)
            VALUES ('youtube', now())
            RETURNING id
            """
        )
        return cur.fetchone()[0]


def finish_run(conn, run_id: int, added: int, rejected: int, units: int, error: str | None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE runs
            SET finished_at = now(), added = %s, rejected = %s, units = %s, error = %s
            WHERE id = %s
            """,
            (added, rejected, units, error, run_id),
        )


def process_brand(conn, yt: YouTube, brand: dict) -> dict:
    own = refresh_own_videos(conn, yt, brand)
    searched, other = discover_other_videos(conn, yt, brand)
    conn.commit()
    due = videos_due(conn, brand["brand_id"])
    added = rejected = truncated = 0
    reasons: dict[str, int] = {}
    errors: list[Exception] = []
    if due:
        print(f"  {brand['name']}: comments on {len(due)} videos", flush=True)
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = [pool.submit(fetch_video, conn, yt, brand, video) for video in due]
            for future in as_completed(futures):
                try:
                    result = future.result()
                except Exception as exc:
                    errors.append(exc)
                    continue
                added += result["added"]
                rejected += result["rejected"]
                truncated += result["truncated"]
                for reason, count in result["reasons"].items():
                    reasons[reason] = reasons.get(reason, 0) + count
    if errors:
        for exc in errors:
            if isinstance(exc, QuotaExceeded):
                raise exc
        raise errors[0]
    return {
        "own": len(own),
        "other": other,
        "searched": searched,
        "added": added,
        "rejected": rejected,
        "truncated": truncated,
        "reasons": reasons,
    }


def refresh_own_videos(conn, yt: YouTube, brand: dict) -> list[str]:
    playlist = "UU" + brand["youtube_channel_id"][2:]
    try:
        data = yt.get(
            "playlistItems",
            {
                "part": "snippet",
                "playlistId": playlist,
                "maxResults": OWN_VIDEO_COUNT,
            },
        )
    except YouTubeError:
        info = yt.get("channels", {"part": "contentDetails", "id": brand["youtube_channel_id"]})
        items = info.get("items") or []
        if not items:
            raise
        playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        data = yt.get(
            "playlistItems",
            {
                "part": "snippet",
                "playlistId": playlist,
                "maxResults": OWN_VIDEO_COUNT,
            },
        )
    ids: list[str] = []
    rows = []
    for item in data.get("items") or []:
        snippet = item.get("snippet") or {}
        video_id = (snippet.get("resourceId") or {}).get("videoId")
        if not video_id:
            continue
        ids.append(video_id)
        rows.append((video_id, brand["youtube_channel_id"], snippet.get("title") or ""))
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE videos SET active = false WHERE brand_id = %s AND surface = 'own'",
            (brand["brand_id"],),
        )
        for video_id, channel_id, title in rows:
            cur.execute(
                """
                INSERT INTO videos (brand_id, video_id, channel_id, surface, title, active)
                VALUES (%s, %s, %s, 'own', %s, true)
                ON CONFLICT (brand_id, video_id) DO UPDATE SET
                  channel_id = EXCLUDED.channel_id,
                  surface = 'own',
                  title = EXCLUDED.title,
                  active = true
                """,
                (brand["brand_id"], video_id, channel_id, title),
            )
    return ids


def discover_other_videos(conn, yt: YouTube, brand: dict) -> tuple[bool, int]:
    day = datetime.now(EASTERN).date()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT passes FROM discovery_passes WHERE brand_id = %s AND day = %s",
            (brand["brand_id"], day),
        )
        row = cur.fetchone()
    if row and row[0] >= SEARCH_PASSES_PER_DAY:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) FROM videos
                WHERE brand_id = %s AND surface = 'other' AND active
                """,
                (brand["brand_id"],),
            )
            return False, cur.fetchone()[0]

    after = (datetime.now(timezone.utc) - timedelta(days=OTHER_LOOKBACK_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    found: dict[str, dict] = {}
    terms = brand["search_terms"] or [brand["name"]]
    for term in terms:
        data = yt.get(
            "search",
            {
                "part": "snippet",
                "q": f'"{term}"',
                "type": "video",
                "order": "viewCount",
                "publishedAfter": after,
                "maxResults": SEARCH_RESULTS,
            },
        )
        for item in data.get("items") or []:
            snippet = item.get("snippet") or {}
            video_id = (item.get("id") or {}).get("videoId")
            channel_id = snippet.get("channelId")
            if not video_id or channel_id == brand["youtube_channel_id"]:
                continue
            blob = f"{snippet.get('title') or ''} {snippet.get('description') or ''}"
            if not names_brand(blob, brand):
                continue
            found[video_id] = {
                "video_id": video_id,
                "channel_id": channel_id,
                "title": snippet.get("title") or "",
            }
    ranked = rank_by_comments(yt, found)
    chosen = ranked[:OTHER_VIDEO_COUNT]
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE videos SET active = false WHERE brand_id = %s AND surface = 'other'",
            (brand["brand_id"],),
        )
        for video in chosen:
            cur.execute(
                """
                INSERT INTO videos (
                  brand_id, video_id, channel_id, surface, title, comment_count, active
                ) VALUES (%s, %s, %s, 'other', %s, %s, true)
                ON CONFLICT (brand_id, video_id) DO UPDATE SET
                  channel_id = EXCLUDED.channel_id,
                  surface = 'other',
                  title = EXCLUDED.title,
                  comment_count = EXCLUDED.comment_count,
                  active = true
                """,
                (
                    brand["brand_id"],
                    video["video_id"],
                    video["channel_id"],
                    video["title"],
                    video["comment_count"],
                ),
            )
        cur.execute(
            """
            INSERT INTO discovery_passes (brand_id, day, passes, last_at)
            VALUES (%s, %s, 1, now())
            ON CONFLICT (brand_id, day) DO UPDATE SET
              passes = discovery_passes.passes + 1,
              last_at = now()
            """,
            (brand["brand_id"], day),
        )
    return True, len(chosen)


def rank_by_comments(yt: YouTube, found: dict[str, dict]) -> list[dict]:
    if not found:
        return []
    ids = list(found)
    ranked = []
    for start in range(0, len(ids), 50):
        chunk = ids[start : start + 50]
        data = yt.get("videos", {"part": "statistics", "id": ",".join(chunk)})
        for item in data.get("items") or []:
            video = found.get(item["id"])
            if not video:
                continue
            count = int((item.get("statistics") or {}).get("commentCount") or 0)
            if count <= 0:
                continue
            video["comment_count"] = count
            ranked.append(video)
    ranked.sort(key=lambda video: video["comment_count"], reverse=True)
    return ranked


def names_brand(blob: str, brand: dict) -> bool:
    folded = fold(blob)
    terms = brand["search_terms"] or [brand["name"]]
    return any(fold(term) in folded for term in terms if term)


def fold(value: str) -> str:
    return value.lower().replace("'", "").replace("\u2019", "")


def videos_due(conn, brand_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT video_id, channel_id, surface
            FROM videos
            WHERE brand_id = %s
              AND active
              AND (
                last_comment_fetch_at IS NULL
                OR last_comment_fetch_at < now() - %s
              )
            """,
            (brand_id, COMMENT_REFRESH),
        )
        return [
            {"video_id": video_id, "channel_id": channel_id, "surface": surface}
            for video_id, channel_id, surface in cur.fetchall()
        ]


def fetch_video(conn, yt: YouTube, brand: dict, video: dict) -> dict:
    added = rejected = truncated = 0
    reasons: dict[str, int] = {}
    rows = []
    try:
        threads = list(comment_threads(yt, video["video_id"]))
    except CommentsDisabled:
        mark_fetched(conn, brand["brand_id"], video["video_id"])
        return {"added": 0, "rejected": 0, "truncated": 0, "reasons": {}}
    for thread in threads:
        kind, row, reason, cut = mention_from_thread(yt, brand, video, thread)
        if cut:
            truncated += 1
        if kind == "reject":
            rejected += 1
            reasons[reason] = reasons.get(reason, 0) + 1
            continue
        if kind == "keep":
            rows.append(row)
    with _db_lock:
        for row in rows:
            if insert_mention(conn, row):
                added += 1
        _mark_fetched(conn, brand["brand_id"], video["video_id"])
        conn.commit()
    return {"added": added, "rejected": rejected, "truncated": truncated, "reasons": reasons}


def comment_threads(yt: YouTube, video_id: str):
    token = None
    pages = 0
    while pages < THREAD_PAGES:
        params = {
            "part": "snippet,replies",
            "videoId": video_id,
            "maxResults": 100,
            "order": "time",
            "textFormat": "plainText",
        }
        if token:
            params["pageToken"] = token
        data = yt.get("commentThreads", params)
        pages += 1
        yield from data.get("items") or []
        token = data.get("nextPageToken")
        if not token:
            return


def mention_from_thread(yt: YouTube, brand: dict, video: dict, thread: dict):
    snippet = thread.get("snippet") or {}
    top = snippet.get("topLevelComment") or {}
    top_snippet = top.get("snippet") or {}
    native_id = top.get("id")
    text = (top_snippet.get("textOriginal") or top_snippet.get("textDisplay") or "").strip()
    published = top_snippet.get("publishedAt")
    author_channel = (top_snippet.get("authorChannelId") or {}).get("value")
    if author_channel and author_channel == brand["youtube_channel_id"]:
        return "skip", None, None, False
    if video["surface"] == "other" and author_channel and author_channel == video["channel_id"]:
        return "skip", None, None, False
    if not native_id or not video["video_id"]:
        return "reject", None, "no_url", False
    if not text:
        return "reject", None, "no_text", False
    if not published:
        return "reject", None, "no_time", False
    inline = ((thread.get("replies") or {}).get("comments") or [])
    total = int(snippet.get("totalReplyCount") or 0)
    replied, reply_text, truncated = resolve_brand_reply(
        yt, brand["youtube_channel_id"], total, top.get("id"), inline
    )
    row = {
        "posted_at": datetime.fromisoformat(published.replace("Z", "+00:00")),
        "brand_id": brand["brand_id"],
        "surface": video["surface"],
        "native_id": native_id,
        "url": f"https://www.youtube.com/watch?v={video['video_id']}&lc={native_id}",
        "author": (top_snippet.get("authorDisplayName") or "").lstrip("@") or None,
        "text": text,
        "parent_url": f"https://www.youtube.com/watch?v={video['video_id']}",
        "brand_replied": replied,
        "reply_text": reply_text,
    }
    return "keep", row, None, truncated


def resolve_brand_reply(yt: YouTube, channel_id: str, total: int, parent_id: str, inline: list):
    """commentThreads inlines at most 5 replies. Above that, page comments.list.

    Paging stops once the brand channel is found, and otherwise continues until the
    replies end. A scan that hits the page cap leaves brand_replied unknown.
    """
    if total > 5:
        if not parent_id:
            return None, None, True
        replies, truncated = yt.all_replies(parent_id, channel_id, REPLY_PAGE_CAP)
        return _status_from_replies(replies, channel_id, truncated)
    if total > len(inline) and parent_id:
        replies, truncated = yt.all_replies(parent_id, channel_id, REPLY_PAGE_CAP)
        return _status_from_replies(replies, channel_id, truncated)
    return _status_from_replies(inline, channel_id, False)


def _status_from_replies(replies: list[dict], channel_id: str, truncated: bool):
    hits = []
    for item in replies:
        snippet = item.get("snippet") or {}
        author = (snippet.get("authorChannelId") or {}).get("value")
        if author == channel_id:
            hits.append(snippet)
    if hits:
        hits.sort(key=lambda snippet: snippet.get("publishedAt") or "")
        text = (hits[0].get("textOriginal") or hits[0].get("textDisplay") or "").strip() or None
        return True, text, False
    if truncated:
        return None, None, True
    return False, None, False


def insert_mention(conn, row: dict) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO mentions (
              posted_at, brand_id, platform, surface, native_id, url, author, text,
              parent_url, brand_replied, reply_text, proof, collected_by
            ) VALUES (
              %(posted_at)s, %(brand_id)s, 'youtube', %(surface)s, %(native_id)s, %(url)s,
              %(author)s, %(text)s, %(parent_url)s, %(brand_replied)s, %(reply_text)s,
              'api', 'youtube'
            )
            ON CONFLICT (platform, native_id, posted_at) DO NOTHING
            RETURNING 1
            """,
            row,
        )
        if cur.fetchone():
            return True
        cur.execute(
            """
            UPDATE mentions SET
              author = %(author)s,
              text = %(text)s,
              url = %(url)s,
              parent_url = %(parent_url)s,
              surface = %(surface)s,
              brand_replied = CASE
                WHEN brand_replied IS TRUE THEN TRUE
                WHEN %(brand_replied)s IS NULL THEN brand_replied
                ELSE %(brand_replied)s
              END,
              reply_text = COALESCE(%(reply_text)s, reply_text),
              proof = 'api',
              collected_by = 'youtube',
              collected_at = now()
            WHERE platform = 'youtube'
              AND native_id = %(native_id)s
              AND posted_at = %(posted_at)s
            """,
            row,
        )
    return False


def mark_fetched(conn, brand_id: str, video_id: str) -> None:
    with _db_lock:
        _mark_fetched(conn, brand_id, video_id)
        conn.commit()


def _mark_fetched(conn, brand_id: str, video_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE videos
            SET last_comment_fetch_at = now()
            WHERE brand_id = %s AND video_id = %s
            """,
            (brand_id, video_id),
        )


def report(conn, yt: YouTube, added: int, rejected: int, reasons: dict, truncated: int, notes: list[str]) -> None:
    print("")
    print(f"units {yt.units}  breakdown {yt.by_method}")
    print(f"added {added}  rejected {rejected}  reasons {reasons or {}}  reply_scans_cut_short {truncated}")
    if notes:
        print("notes:")
        for note in notes:
            print(f"  {note}")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT b.name, count(m.native_id)
            FROM brands b
            LEFT JOIN mentions m ON m.brand_id = b.id
            GROUP BY b.name
            ORDER BY count(m.native_id) DESC, b.name
            """
        )
        print("rows per brand:")
        for name, count in cur.fetchall():
            print(f"  {name}: {count}")
        cur.execute(
            """
            SELECT id, added, rejected, units, error
            FROM runs
            ORDER BY id DESC
            LIMIT 1
            """
        )
        run = cur.fetchone()
        print(f"latest run: id {run[0]} added {run[1]} rejected {run[2]} units {run[3]} error {run[4]}")
        cur.execute("SELECT url FROM mentions ORDER BY random() LIMIT 5")
        print("sample urls:")
        urls = cur.fetchall()
        if not urls:
            print("  none")
        for (url,) in urls:
            print(f"  {url}")


if __name__ == "__main__":
    main()
