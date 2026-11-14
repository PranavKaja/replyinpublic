"""One EnsembleData TikTok pull for the focus brands.

Budget: 1 unit for 10 posts per brand, then 1 unit for 30 comments on each of
2 posts. Five brands is 15 units. Replies are not requested, so brand_replied
stays null.
"""

from __future__ import annotations

import os
import urllib.parse
import urllib.request
import json

from app.collect_social import insert_row, load_focus, parse_time, start_run, finish_run
from app.db import connect, load_env
from app.segment import ensure_labels, is_noise, save_label

ROOT_URL = "https://ensembledata.com/apis"


def get(path: str, params: dict) -> dict:
    load_env()
    token = os.environ.get("ENSEMBLEDATA_API_KEY", "").strip()
    if not token:
        raise SystemExit("ENSEMBLEDATA_API_KEY is missing from .env")
    params = {**params, "token": token}
    url = ROOT_URL + path + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def posts_for(username: str) -> list[dict]:
    payload = get("/tt/user/posts", {
        "username": username,
        "depth": 1,
        "start_cursor": 0,
        "download_video": "false",
    })
    data = payload.get("data") or []
    if isinstance(data, dict):
        data = data.get("data") or data.get("aweme_list") or []
    return data if isinstance(data, list) else []


def comments_for(aweme_id: str) -> list[dict]:
    payload = get("/tt/post/comments", {"aweme_id": aweme_id, "cursor": 0})
    data = payload.get("data") or {}
    if isinstance(data, dict):
        return data.get("comments") or []
    return data if isinstance(data, list) else []


def aweme_id(post: dict) -> str:
    stats = post.get("statistics") or post.get("stats") or {}
    return str(post.get("aweme_id") or post.get("id") or stats.get("aweme_id") or "")


def comment_count(post: dict) -> int:
    stats = post.get("statistics") or post.get("stats") or {}
    return int(stats.get("comment_count") or post.get("comment_count") or 0)


def main() -> None:
    with connect() as conn:
        ensure_labels(conn)
        brands = load_focus(conn)
        run_id = start_run(conn, "tiktok-ensemble")
        added = rejected = 0
        notes = []
        for brand in brands:
            handle = (brand["instagram_handle"] or "").lstrip("@")
            if not handle:
                notes.append(f"{brand['name']}: no handle")
                continue
            try:
                posts = posts_for(handle)
            except Exception as exc:
                notes.append(f"{brand['name']}: {exc.__class__.__name__}")
                print(f"{brand['name']}: posts failed {exc}", flush=True)
                continue
            print(f"{brand['name']}: {len(posts)} posts", flush=True)
            ranked = sorted(posts, key=comment_count, reverse=True)[:2]
            for post in ranked:
                video_id = aweme_id(post)
                if not video_id:
                    continue
                try:
                    comments = comments_for(video_id)
                except Exception as exc:
                    notes.append(f"{brand['name']} {video_id}: {exc.__class__.__name__}")
                    continue
                video_url = f"https://www.tiktok.com/@{handle}/video/{video_id}"
                print(f"  {video_id}: {len(comments)} comments", flush=True)
                for comment in comments:
                    text = (comment.get("text") or "").strip()
                    cid = str(comment.get("cid") or "")
                    user = comment.get("user") or {}
                    author = user.get("unique_id") or user.get("nickname") or ""
                    kind = insert_row(conn, {
                        "posted_at": parse_time(comment.get("create_time")),
                        "brand_id": brand["id"],
                        "platform": "tiktok",
                        "surface": "own",
                        "native_id": cid,
                        "url": f"{video_url}?cid={cid}" if cid else "",
                        "author": str(author).lstrip("@") or None,
                        "text": text,
                        "parent_url": video_url,
                        "brand_replied": None,
                        "reply_text": None,
                        "proof": "none",
                        "collected_by": "ensembledata",
                    })
                    if kind == "added":
                        added += 1
                        if is_noise(text):
                            with conn.cursor() as cur:
                                cur.execute(
                                    """
                                    SELECT id, posted_at FROM mentions
                                    WHERE platform = 'tiktok' AND native_id = %s
                                    ORDER BY collected_at DESC LIMIT 1
                                    """,
                                    (cid,),
                                )
                                saved = cur.fetchone()
                            if saved:
                                save_label(conn, saved[0], saved[1], {
                                    "type": "noise",
                                    "sentiment": "neutral",
                                    "urgency": "low",
                                    "is_buyer": False,
                                    "relevant": False,
                                    "model": "rules",
                                    "topic": None,
                                })
                    elif kind == "reject":
                        rejected += 1
            conn.commit()
        finish_run(conn, run_id, added, rejected, "; ".join(notes)[:2000] or None)
        print(f"tiktok ensemble added {added} rejected {rejected}", flush=True)


if __name__ == "__main__":
    main()
