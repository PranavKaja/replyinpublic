"""Local preview of the comments already stored in Tiger."""

import json
import os
import threading
import urllib.request
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from app.db import ROOT, connect, load_env
from app.hooks import mark_publish_demo, save_reply_draft, update_draft_status
from app.ingest import ingest_records, parse_raw_lines

app = FastAPI(title="ReplyInPublic")
_conn = None
_lock = threading.Lock()


def db():
    global _conn
    if _conn is None or _conn.closed:
        _conn = connect()
    return _conn


@app.get("/favicon.ico", include_in_schema=False)
@app.get("/favicon.png", include_in_schema=False)
def favicon_png():
    return FileResponse(ROOT / "app" / "brand" / "favicon.png", media_type="image/png")


@app.get("/favicon.svg", include_in_schema=False)
def favicon_svg():
    return FileResponse(ROOT / "app" / "brand" / "favicon.svg", media_type="image/svg+xml")


@app.get("/brand/overheard-logo.png", include_in_schema=False)
def brand_logo():
    return FileResponse(ROOT / "app" / "brand" / "overheard-logo.png", media_type="image/png")


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return (ROOT / "app" / "landing.html").read_text(encoding="utf-8")


@app.get("/app", response_class=HTMLResponse)
def workspace() -> str:
    return (ROOT / "app" / "crm.html").read_text(encoding="utf-8")


@app.get("/console", response_class=HTMLResponse)
def console() -> str:
    return (ROOT / "app" / "crm.html").read_text(encoding="utf-8")


@app.get("/api/public")
def public_stats() -> dict:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT platform, count(*) FROM mentions GROUP BY 1 ORDER BY 2 DESC")
            platforms = [{"platform": name, "count": count} for name, count in cur.fetchall()]
            cur.execute("SELECT count(*) FROM mentions")
            total = cur.fetchone()[0]
            cur.execute(
                """
                SELECT count(*) FROM mentions m
                LEFT JOIN labels l ON l.mention_id = m.id AND l.posted_at = m.posted_at
                WHERE COALESCE(l.relevant, true) IS TRUE
                  AND l.type IN ('complaint', 'question', 'purchase_intent')
                """
            )
            actionable = cur.fetchone()[0]
            cur.execute("SELECT count(DISTINCT brand_id) FROM kb_chunks")
            kb_brands = cur.fetchone()[0]
    return {
        "mentions": total,
        "actionable": actionable,
        "kb_brands": kb_brands,
        "platforms": platforms,
    }


@app.get("/api/workspace")
def workspace_data() -> dict:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT b.id, b.name, b.support_contact, b.reply_sla_hours,
                       COALESCE(k.chunks, 0)::integer
                FROM brands b
                LEFT JOIN (
                  SELECT brand_id, count(*) AS chunks FROM kb_chunks GROUP BY brand_id
                ) k ON k.brand_id = b.id
                ORDER BY b.name
                """
            )
            brands = [
                {
                    "id": brand_id,
                    "name": name,
                    "support_contact": contact,
                    "reply_sla_hours": sla,
                    "kb_chunks": chunks,
                }
                for brand_id, name, contact, sla, chunks in cur.fetchall()
            ]
            cur.execute(
                """
                SELECT b.name, c.platform, c.status, c.note
                FROM brand_connections c
                JOIN brands b ON b.id = c.brand_id
                ORDER BY b.name, c.platform
                """
            )
            connections = [
                {"brand": name, "platform": platform, "status": status, "note": note}
                for name, platform, status, note in cur.fetchall()
            ]
    return {"brands": brands, "connections": connections}


@app.get("/api/console/summary")
def console_summary() -> dict:
    focus = json.loads((ROOT / "focus.json").read_text(encoding="utf-8"))["brands"]
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM mentions")
            total = cur.fetchone()[0]
            cur.execute(
                """
                SELECT count(*) FROM mentions m
                LEFT JOIN labels l ON l.mention_id = m.id AND l.posted_at = m.posted_at
                WHERE m.brand_replied IS NOT TRUE
                  AND COALESCE(l.relevant, true) IS TRUE
                """
            )
            open_count = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM publish_queue WHERE status = 'queued'")
            queued = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM onboarding_leads WHERE status = 'new'")
            leads_new = cur.fetchone()[0]
            cur.execute(
                """
                SELECT b.name, c.platform, c.status, c.note
                FROM brand_connections c
                JOIN brands b ON b.id = c.brand_id
                WHERE c.brand_id = ANY(%s)
                ORDER BY b.name, c.platform
                """,
                (focus,),
            )
            connections = [
                {"brand": name, "platform": platform, "status": status, "note": note}
                for name, platform, status, note in cur.fetchall()
            ]
            cur.execute(
                """
                SELECT q.id, q.case_id, q.channel, q.body, q.status, q.queued_at
                FROM publish_queue q
                ORDER BY q.queued_at DESC
                LIMIT 25
                """
            )
            publish_queue = [
                {
                    "id": qid,
                    "case_id": case_id,
                    "channel": channel,
                    "body": body,
                    "status": status,
                    "queued_at": queued_at.isoformat() if isinstance(queued_at, datetime) else str(queued_at),
                }
                for qid, case_id, channel, body, status, queued_at in cur.fetchall()
            ]
            cur.execute(
                """
                SELECT company_name, contact_name, contact_email, brand_slug, created_at
                FROM onboarding_leads
                ORDER BY created_at DESC
                LIMIT 10
                """
            )
            leads = [
                {
                    "company_name": company,
                    "contact_name": contact,
                    "contact_email": email,
                    "brand_slug": slug,
                    "created_at": created_at.isoformat() if isinstance(created_at, datetime) else str(created_at),
                }
                for company, contact, email, slug, created_at in cur.fetchall()
            ]
    return {
        "stats": [
            {"label": "Stored mentions", "value": str(total)},
            {"label": "Open (not brand replied)", "value": str(open_count)},
            {"label": "Queued to publish", "value": str(queued)},
            {"label": "New pilot signups", "value": str(leads_new)},
        ],
        "connections": connections,
        "publish_queue": publish_queue,
        "leads": leads,
    }


@app.post("/api/onboard")
async def api_onboard(request: Request) -> dict:
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON body required")
    company = str(payload.get("company_name") or "").strip()
    contact_name = str(payload.get("contact_name") or "").strip()
    email = str(payload.get("contact_email") or "").strip()
    brand_slug = str(payload.get("brand_slug") or "").strip() or None
    kb_url = str(payload.get("kb_url") or "").strip() or None
    platforms = payload.get("platforms") or []
    if not company or not contact_name or not email:
        raise HTTPException(status_code=400, detail="company_name, contact_name, contact_email required")
    if not isinstance(platforms, list):
        platforms = []
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO onboarding_leads (
                  company_name, contact_name, contact_email, brand_slug, kb_url, platforms
                ) VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (company, contact_name, email, brand_slug, kb_url, platforms),
            )
            lead_id = cur.fetchone()[0]
            if brand_slug:
                for platform in platforms:
                    cur.execute(
                        """
                        INSERT INTO brand_connections (brand_id, platform, status, note)
                        VALUES (%s, %s, 'pilot_requested', %s)
                        ON CONFLICT (brand_id, platform) DO UPDATE SET
                          status = 'pilot_requested',
                          note = EXCLUDED.note,
                          updated_at = now()
                        """,
                        (brand_slug, platform, f"Requested by {company}"),
                    )
        conn.commit()
    return {"id": lead_id, "status": "new"}


@app.post("/api/publish/{queue_id}/demo")
def publish_demo(queue_id: int) -> dict:
    with db() as conn:
        ok = mark_publish_demo(conn, queue_id)
    if not ok:
        raise HTTPException(status_code=404, detail="queue row not found or already posted")
    return {"status": "posted_demo", "queue_id": queue_id}


@app.get("/api/preview")
def preview(brand: str = "", unanswered: int = 1, kind: str = "", actionable: int = 0) -> dict:
    with _lock:
        return _preview(brand, unanswered, kind, actionable)


def _preview(brand: str, unanswered: int, kind: str = "", actionable: int = 0) -> dict:
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
            if actionable:
                filters.append("l.type = ANY(%s)")
                params.append(["question", "complaint", "purchase_intent"])
            if kind in {"question", "complaint", "praise", "purchase_intent", "noise"}:
                filters.append("l.type = %s")
                params.append(kind)
            params.append(200)
            cur.execute(
                f"""
                SELECT m.id, b.id, b.name, m.author, m.text, m.url, m.posted_at,
                       m.brand_replied, m.surface, m.reply_text, l.type, m.platform,
                       m.case_id, m.proof, m.brand_reply_at, m.brand_reply_author,
                       b.support_contact, b.reply_sla_hours,
                       d.status, d.draft_text, d.final_text
                FROM mentions m
                JOIN brands b ON b.id = m.brand_id
                LEFT JOIN labels l ON l.mention_id = m.id AND l.posted_at = m.posted_at
                LEFT JOIN reply_drafts d ON d.mention_id = m.id AND d.posted_at = m.posted_at
                WHERE {' AND '.join(filters)}
                ORDER BY m.posted_at DESC
                LIMIT %s
                """,
                params,
            )
            comments = []
            for row in cur.fetchall():
                (
                    mention_id,
                    brand_id,
                    name,
                    author,
                    text,
                    url,
                    posted_at,
                    replied,
                    surface,
                    reply_text,
                    kind,
                    platform,
                    case_id,
                    proof,
                    brand_reply_at,
                    brand_reply_author,
                    support_contact,
                    sla_hours,
                    draft_status,
                    draft_text,
                    final_text,
                ) = row
                posted_iso = posted_at.isoformat() if isinstance(posted_at, datetime) else str(posted_at)
                due_iso = None
                if isinstance(posted_at, datetime) and replied is False and sla_hours:
                    due = posted_at + timedelta(hours=int(sla_hours))
                    due_iso = due.isoformat()
                comments.append({
                    "id": mention_id,
                    "brand_id": brand_id,
                    "brand": name,
                    "author": author,
                    "text": text,
                    "url": url,
                    "posted_at": posted_iso,
                    "brand_replied": replied,
                    "surface": surface,
                    "reply_text": reply_text,
                    "type": kind,
                    "platform": platform,
                    "case_id": case_id,
                    "proof": proof,
                    "brand_reply_at": brand_reply_at.isoformat() if isinstance(brand_reply_at, datetime) else None,
                    "brand_reply_author": brand_reply_author,
                    "support_contact": support_contact,
                    "reply_due_at": due_iso,
                    "draft_status": draft_status,
                    "draft_text": final_text or draft_text,
                })
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


def _load_mention(cur, mention_id: int, posted_at: str):
    if posted_at:
        posted_at = posted_at.strip().replace(" ", "+")
        try:
            cur.execute(
                """
                SELECT m.text, m.brand_id, b.name, m.posted_at, m.case_id,
                       b.support_contact, b.reply_sla_hours
                FROM mentions m
                JOIN brands b ON b.id = m.brand_id
                WHERE m.id = %s AND m.posted_at = %s
                """,
                (mention_id, posted_at),
            )
            row = cur.fetchone()
            if row:
                return row
        except Exception:
            pass
    cur.execute(
        """
        SELECT m.text, m.brand_id, b.name, m.posted_at, m.case_id,
               b.support_contact, b.reply_sla_hours
        FROM mentions m
        JOIN brands b ON b.id = m.brand_id
        WHERE m.id = %s
        ORDER BY m.posted_at DESC
        LIMIT 1
        """,
        (mention_id,),
    )
    return cur.fetchone()


def _passages_for(cur, key: str, text: str, brand_id: str) -> list[dict]:
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
    return passages


@app.get("/api/copilot")
def copilot(mention_id: int, posted_at: str = "", token: str = "") -> dict:
    if not _copilot_allowed(token):
        return {"passages": [], "reply": "copilot token required"}
    load_env()
    key = os.environ.get("GEMINI_API_KEY", "").strip()

    with db() as conn:
        with conn.cursor() as cur:
            row = _load_mention(cur, mention_id, posted_at)
            if not row:
                return {"passages": [], "reply": "not in the manuals, send to the brand's support person"}
            text, brand_id, brand_name, mention_posted_at, case_id, support_contact, sla_hours = row
            passages = _passages_for(cur, key, text, brand_id)
    if not passages:
        return {
            "passages": [],
            "reply": "not in the manuals, send to the brand's support person",
            "case_id": case_id,
            "support_contact": support_contact,
        }
    packed = "\n\n".join(
        f"Source: {item['source_url']}\n{item['text']}" for item in passages
    )
    prompt = (
        f"The brand is {brand_name}. A customer wrote:\n{text}\n\n"
        "Use only the manual passages below. Do not add facts that are not in them. "
        "Do not promise refunds, replacements, or incentives unless the passages say so. "
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
    with db() as conn:
        save_reply_draft(conn, mention_id, mention_posted_at, reply, passages)
    return {
        "passages": passages,
        "reply": reply,
        "case_id": case_id,
        "support_contact": support_contact,
        "reply_sla_hours": sla_hours,
    }


@app.post("/api/draft")
async def api_draft(request: Request, token: str = "") -> dict:
    if not _copilot_allowed(token):
        raise HTTPException(status_code=401, detail="copilot token required")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON body required")
    mention_id = int(payload.get("mention_id") or 0)
    posted_at = str(payload.get("posted_at") or "").strip()
    action = str(payload.get("action") or "").strip().lower()
    final_text = payload.get("final_text")
    publish_channel = str(payload.get("publish_channel") or "public").strip() or "public"
    if not mention_id or not posted_at or action not in {"approve", "edit", "reject"}:
        raise HTTPException(status_code=400, detail="mention_id, posted_at, and action required")
    status = {"approve": "approved", "edit": "edited", "reject": "rejected"}[action]
    with db() as conn:
        ok = update_draft_status(
            conn, mention_id, posted_at, status, final_text, publish_channel=publish_channel
        )
    if not ok:
        raise HTTPException(status_code=404, detail="open copilot on this message first")
    return {"status": status, "mention_id": mention_id}
