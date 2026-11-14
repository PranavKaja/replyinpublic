"""Local preview of the comments already stored in Tiger."""

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
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT brand_id, name, unanswered_14d
                FROM brand_rank
                """
            )
            brands = [
                {"id": brand_id, "name": name, "unanswered_14d": count}
                for brand_id, name, count in cur.fetchall()
            ]
            cur.execute("SELECT count(*) FROM mentions")
            total = cur.fetchone()[0]
            cur.execute(
                """
                SELECT added, rejected, units, finished_at
                FROM runs
                ORDER BY id DESC
                LIMIT 1
                """
            )
            run = cur.fetchone()
            filters = ["TRUE"]
            params: list = []
            if brand:
                filters.append("m.brand_id = %s")
                params.append(brand)
            if unanswered:
                filters.append("m.brand_replied IS FALSE")
            params.append(80)
            cur.execute(
                f"""
                SELECT b.name, m.author, m.text, m.url, m.posted_at,
                       m.brand_replied, m.surface, m.reply_text
                FROM mentions m
                JOIN brands b ON b.id = m.brand_id
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
                }
                for name, author, text, url, posted_at, replied, surface, reply_text in cur.fetchall()
            ]
    return {
        "total": total,
        "run": {
            "added": run[0] if run else 0,
            "rejected": run[1] if run else 0,
            "units": run[2] if run else 0,
            "finished_at": run[3].isoformat() if run and isinstance(run[3], datetime) else None,
        },
        "brands": brands,
        "comments": comments,
    }
