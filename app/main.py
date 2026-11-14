"""Local preview of the comments already stored in Tiger."""

import json
import os
import threading
import urllib.request
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.db import ROOT, connect, load_env
from app.ingest import ingest_records, parse_raw_lines

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
                SELECT m.id, b.id, b.name, m.author, m.text, m.url, m.posted_at,
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
                    "id": mention_id,
                    "brand_id": brand_id,
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
                for mention_id, brand_id, name, author, text, url, posted_at, replied, surface, reply_text, kind, platform in cur.fetchall()
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


def _embed(key: str, text: str) -> list[float]:
    body = json.dumps({
        "content": {"parts": [{"text": text[:6000]}]},
        "outputDimensionality": 768,
    }).encode()
    request = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key=" + key,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    return payload["embedding"]["values"]


def _copilot_allowed(token: str) -> bool:
    load_env()
    required = os.environ.get("COPILOT_TOKEN", "").strip()
    if not required:
        return True
    return token.strip() == required


@app.post("/api/ingest")
async def api_ingest(request: Request, token: str = "") -> dict:
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.headers.get("x-token", "")
    if not _copilot_allowed(token):
        raise HTTPException(status_code=401, detail="copilot token required")

    try:
        raw_body = await request.body()
        text_body = raw_body.decode("utf-8")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid body: {exc}")

    items = []
    try:
        data = json.loads(text_body)
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            if "items" in data and isinstance(data["items"], list):
                items = data["items"]
            elif "raw" in data and isinstance(data["raw"], str):
                items = parse_raw_lines(data["raw"])
            else:
                items = [data]
        elif isinstance(data, str):
            items = parse_raw_lines(data)
    except Exception:
        items = parse_raw_lines(text_body)

    if not items:
        return {"status": "empty", "message": "No valid JSON or lines found in request body", "added": 0}

    with db() as conn:
        result = ingest_records(conn, items)
    return result


@app.get("/api/copilot")
def copilot(mention_id: int, posted_at: str, token: str = "") -> dict:
    if not _copilot_allowed(token):
        return {"passages": [], "reply": "copilot token required"}
    load_env()
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.text, m.brand_id, b.name
                FROM mentions m
                JOIN brands b ON b.id = m.brand_id
                WHERE m.id = %s AND m.posted_at = %s
                """,
                (mention_id, posted_at),
            )
            row = cur.fetchone()
            if not row:
                return {"passages": [], "reply": "not in the manuals, send to the brand's support person"}
            text, brand_id, brand_name = row
            passages = []
            try:
                vector = _embed(key, text)
                cur.execute(
                    """
                    SELECT text, source_url, embedding <=> %s::vector AS distance
                    FROM kb_chunks
                    WHERE brand_id = %s AND embedding IS NOT NULL
                    ORDER BY embedding <=> %s::vector
                    LIMIT 3
                    """,
                    (str(vector), brand_id, str(vector)),
                )
                passages = [
                    {"text": chunk, "source_url": url, "distance": float(distance)}
                    for chunk, url, distance in cur.fetchall()
                ]
            except Exception:
                passages = []
            if not passages:
                words = {word.lower() for word in text.split() if len(word) > 3}
                cur.execute(
                    "SELECT text, source_url FROM kb_chunks WHERE brand_id = %s",
                    (brand_id,),
                )
                scored = []
                for chunk, url in cur.fetchall():
                    overlap = sum(1 for word in words if word in chunk.lower())
                    scored.append((overlap, chunk, url))
                scored.sort(reverse=True)
                passages = [
                    {"text": chunk, "source_url": url, "distance": None}
                    for overlap, chunk, url in scored[:3]
                    if overlap > 0
                ]
    if not passages:
        return {"passages": [], "reply": "not in the manuals, send to the brand's support person"}
    packed = "\n\n".join(
        f"Source: {item['source_url']}\n{item['text']}" for item in passages
    )
    prompt = (
        f"The brand is {brand_name}. A customer wrote:\n{text}\n\n"
        "Use only the manual passages below. Do not add facts that are not in them. "
        "If they do not answer the customer, reply with exactly: "
        "not in the manuals, send to the brand's support person\n"
        "Otherwise write a short public reply in one or two sentences.\n\n"
        + packed
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }).encode()
    request = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key=" + key,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.load(response)
        reply = ""
        for candidate in payload.get("candidates") or []:
            for part in (candidate.get("content") or {}).get("parts") or []:
                reply += part.get("text") or ""
        reply = reply.strip() or "not in the manuals, send to the brand's support person"
    except Exception:
        reply = "not in the manuals, send to the brand's support person"
    return {"passages": passages, "reply": reply}
