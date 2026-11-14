"""Local preview of the comments already stored in Tiger."""

import json
import threading
from datetime import datetime

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.db import ROOT, connect

app = FastAPI(title="ReplyInPublic")
_conn = None
_lock = threading.Lock()


def db():
    global _conn
    if _conn is None or _conn.closed:
        _conn = connect()
    return _conn


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return (ROOT / "app" / "preview.html").read_text(encoding="utf-8")


@app.get("/api/preview")
def preview(brand: str = "", unanswered: int = 1) -> dict:
    with _lock:
        return _preview(brand, unanswered)


def _preview(brand: str, unanswered: int) -> dict:
    focus = json.loads((ROOT / "focus.json").read_text(encoding="utf-8"))["brands"]
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT b.id, b.name,
                       count(m.id) FILTER (
                         WHERE m.brand_replied IS NOT TRUE
                           AND m.posted_at >= now() - interval '14 days'
                           AND COALESCE(l.relevant, true) IS TRUE
                       )::integer AS inbox_14d
                FROM brands b
                LEFT JOIN mentions m ON m.brand_id = b.id
                LEFT JOIN labels l ON l.mention_id = m.id AND l.posted_at = m.posted_at
                GROUP BY b.id, b.name
                ORDER BY inbox_14d DESC, b.name
                """
            )
            brands = [
                {"id": brand_id, "name": name, "unanswered_14d": count, "focus": brand_id in focus}
                for brand_id, name, count in cur.fetchall()
            ]
            cur.execute(
                """
                SELECT count(*)
                FROM mentions m
                LEFT JOIN labels l ON l.mention_id = m.id AND l.posted_at = m.posted_at
                WHERE COALESCE(l.relevant, true) IS TRUE
                """
            )
            visible = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM mentions")
            total = cur.fetchone()[0]
            cur.execute(
                """
                SELECT COALESCE(l.type, 'unlabeled'), count(*)
                FROM mentions m
                LEFT JOIN labels l ON l.mention_id = m.id AND l.posted_at = m.posted_at
                WHERE m.brand_id = ANY(%s)
                GROUP BY 1
                ORDER BY 2 DESC
                """
                ,
                (focus,),
            )
            segments = [{"type": kind, "count": count} for kind, count in cur.fetchall()]
            cur.execute(
                """
                SELECT to_char(date_trunc('day', m.posted_at), 'MM-DD') AS day, count(*)
                FROM mentions m
                LEFT JOIN labels l ON l.mention_id = m.id AND l.posted_at = m.posted_at
                WHERE m.brand_id = ANY(%s)
                  AND COALESCE(l.relevant, true) IS TRUE
                  AND m.posted_at >= now() - interval '14 days'
                GROUP BY date_trunc('day', m.posted_at)
                ORDER BY date_trunc('day', m.posted_at)
                """
                ,
                (focus,),
            )
            days = [{"day": day, "count": count} for day, count in cur.fetchall()]
            cur.execute(
                """
                SELECT added, rejected, units, finished_at, source
                FROM runs
                ORDER BY id DESC
                LIMIT 1
                """
            )
            run = cur.fetchone()
            filters = ["COALESCE(l.relevant, true) IS TRUE"]
            params: list = []
            if brand:
                filters.append("m.brand_id = %s")
                params.append(brand)
            elif not brand:
                filters.append("m.brand_id = ANY(%s)")
                params.append(focus)
            if unanswered:
                filters.append("m.brand_replied IS NOT TRUE")
            params.append(80)
            cur.execute(
                f"""
                SELECT b.name, m.author, m.text, m.url, m.posted_at,
                       m.brand_replied, m.surface, m.reply_text, l.type, m.platform
                FROM mentions m
                JOIN brands b ON b.id = m.brand_id
                LEFT JOIN labels l ON l.mention_id = m.id AND l.posted_at = m.posted_at
                WHERE {' AND '.join(filters)}
                ORDER BY m.posted_at DESC
                LIMIT %s
                """,
                params,
            )
            comments = [
                {
                    "brand": name,
                    "author": author,
                    "text": text,
                    "url": url,
                    "posted_at": posted_at.isoformat() if isinstance(posted_at, datetime) else str(posted_at),
                    "brand_replied": replied,
                    "surface": surface,
                    "reply_text": reply_text,
                    "type": kind,
                    "platform": platform,
                }
                for name, author, text, url, posted_at, replied, surface, reply_text, kind, platform in cur.fetchall()
            ]
    return {
        "total": total,
        "visible": visible,
        "focus": focus,
        "segments": segments,
        "days": days,
        "run": {
            "added": run[0] if run else 0,
            "rejected": run[1] if run else 0,
            "units": run[2] if run else 0,
            "finished_at": run[3].isoformat() if run and isinstance(run[3], datetime) else None,
            "source": run[4] if run else None,
        },
        "brands": brands,
        "comments": comments,
    }
