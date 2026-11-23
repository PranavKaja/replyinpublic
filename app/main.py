"""Local preview of the comments already stored in Tiger."""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import threading
import time
import urllib.request
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.db import ROOT, connect, load_env
from app.hooks import mark_publish_demo, save_reply_draft, update_draft_status
from app.ingest import ingest_records, parse_raw_lines

app = FastAPI(title="ReplyInPublic")
log = logging.getLogger("replyinpublic")
_conn = None
_lock = threading.Lock()


def db():
    global _conn
    if _conn is None or _conn.closed:
        _conn = connect()
    return _conn


DIST = ROOT / "web" / "dist"
app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


def _spa() -> FileResponse:
    return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/")
def home() -> FileResponse:
    return _spa()


@app.get("/inbox")
@app.get("/login")
def inbox_page() -> FileResponse:
    return _spa()


@app.get("/favicon.svg")
def favicon_svg() -> FileResponse:
    return FileResponse(DIST / "favicon.svg")


@app.get("/favicon.png")
@app.get("/favicon.ico")
def favicon_png() -> FileResponse:
    return FileResponse(DIST / "favicon.png")


@app.get("/app")
@app.get("/console")
def old_workspace_links() -> RedirectResponse:
    return RedirectResponse("/inbox")


@app.get("/old", response_class=HTMLResponse)
def old_landing() -> str:
    return (ROOT / "app" / "landing.html").read_text(encoding="utf-8")


@app.get("/old/app", response_class=HTMLResponse)
def old_workspace() -> str:
    return (ROOT / "app" / "crm.html").read_text(encoding="utf-8")


DESK_STATUSES = {"inbox", "parked", "snoozed", "handled", "dismissed", "feedback"}
_URGENCY_POINTS = {"high": 60, "medium": 40, "low": 20}
SESSION_COOKIE = "rip_session"
SESSION_DAYS = 7
_USERNAME = re.compile(r"[a-z0-9_-]{1,64}")
_EXPIRES = re.compile(r"[0-9]{1,12}")


def _focus() -> list:
    return json.loads((ROOT / "focus.json").read_text(encoding="utf-8"))["brands"]


def _desk_users() -> dict:
    """Two kinds of account. A brand team sees its own brand. The ReplyInPublic team sees them all.

    Accounts come only from DESK_USERS in the environment, as JSON:
    {"pranav": {"password": "...", "role": "rip", "name": "Pranav Kaja", "brands": "*"},
     "nespresso": {"password": "...", "role": "brand", "name": "Nespresso team", "brands": ["nespresso"]}}
    If DESK_USERS is missing or broken, nobody can sign in. Usernames are lowercase letters,
    digits, _ or -. An account with no password, or with brands that are not "*" or a list, is skipped.
    """
    load_env()
    raw = os.environ.get("DESK_USERS", "").strip()
    if not raw:
        return {}
    try:
        users = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("DESK_USERS is not valid JSON, so nobody can sign in")
        return {}
    if not isinstance(users, dict):
        log.warning("DESK_USERS must be a JSON object, so nobody can sign in")
        return {}
    accounts = {}
    for name, user in users.items():
        key = str(name).strip().lower()
        brands = user.get("brands") if isinstance(user, dict) else None
        if not _USERNAME.fullmatch(key) or not isinstance(user, dict):
            log.warning("DESK_USERS account %r skipped: bad username or not an object", name)
        elif not isinstance(user.get("password"), str) or not user["password"]:
            log.warning("DESK_USERS account %r skipped: no password", key)
        elif brands not in (None, "*") and not (isinstance(brands, list) and all(isinstance(b, str) for b in brands)):
            log.warning("DESK_USERS account %r skipped: brands must be \"*\" or a list", key)
        else:
            accounts[key] = user
    return accounts


def _session_secret() -> bytes:
    load_env()
    seed = os.environ.get("SESSION_SECRET") or os.environ.get("DATABASE_URL", "") + "desk-session"
    return hashlib.sha256(seed.encode()).digest()


def _sign(username: str, expires: int, password: str) -> str:
    """The password is part of the key, so changing a password signs that account out everywhere."""
    body = f"{username}.{expires}"
    key = _session_secret() + hashlib.sha256(password.encode()).digest()
    return body + "." + hmac.new(key, body.encode(), hashlib.sha256).hexdigest()


def _session(request: Request) -> dict:
    """The signed-in account, or a 401. Scope comes from the server, never from the browser."""
    token = request.cookies.get(SESSION_COOKIE, "")
    username, _, rest = token.partition(".")
    expires, _, _sig = rest.partition(".")
    user = _desk_users().get(username)
    if (
        not user
        or not _EXPIRES.fullmatch(expires)
        or int(expires) < time.time()
        or not hmac.compare_digest(
            token.encode("utf-8", "replace"), _sign(username, int(expires), user["password"]).encode()
        )
    ):
        raise HTTPException(status_code=401, detail="sign in")
    focus = _focus()
    brands = focus if user.get("brands") == "*" else [b for b in user.get("brands") or [] if b in focus]
    return {"username": username, "role": user.get("role", "brand"), "name": user.get("name", username), "brands": brands}


@app.post("/api/desk/login")
async def desk_login(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    username = str(body.get("username", "")).strip().lower()
    password = str(body.get("password", ""))
    user = _desk_users().get(username)
    expected = (user or {}).get("password", "")
    if not user or not hmac.compare_digest(password.encode("utf-8", "replace"), str(expected).encode()):
        await asyncio.sleep(0.4)  # time.sleep here would stall every other request
        raise HTTPException(status_code=401, detail="wrong username or password")
    expires = int(time.time()) + SESSION_DAYS * 86400
    response = JSONResponse({"ok": True})
    response.set_cookie(
        SESSION_COOKIE,
        _sign(username, expires, expected),
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=request.headers.get("x-forwarded-proto", request.url.scheme) == "https",
        path="/",
    )
    return response


@app.post("/api/desk/logout")
def desk_logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


def _in_scope(conn, mention_id: int, brands: list) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM mentions WHERE id = %s AND brand_id = ANY(%s) LIMIT 1", (mention_id, brands))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="not found")


@app.get("/api/desk/data")
def desk_data(request: Request) -> dict:
    """Brands, issues and messages in the shape the workspace reads, limited to the account's brands."""
    me = _session(request)
    focus = me["brands"]
    with _lock:
        conn = db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, reply_sla_hours FROM brands WHERE id = ANY(%s) ORDER BY name",
                (focus,),
            )
            brands = [
                {"id": bid, "slug": bid, "name": name, "category": "kitchen", "grace_hours": sla or 48}
                for bid, name, sla in cur.fetchall()
            ]
            cur.execute(
                """
                SELECT m.id, m.brand_id, m.platform, m.surface, m.url, m.parent_url, v.title,
                       m.author, m.text, m.posted_at, m.brand_replied, m.reply_text, m.proof,
                       l.type, l.urgency, l.is_buyer,
                       s.status, s.snoozed_until, s.status_changed_at, s.is_feedback, s.draft,
                       t.theme_id
                FROM mentions m
                JOIN LATERAL (
                  SELECT type, urgency, is_buyer FROM labels
                  WHERE mention_id = m.id AND posted_at = m.posted_at
                  ORDER BY labeled_at DESC NULLS LAST LIMIT 1
                ) l ON true
                LEFT JOIN videos v
                  ON m.platform = 'youtube' AND v.brand_id = m.brand_id
                 AND v.video_id = split_part(split_part(m.parent_url, 'v=', 2), '&', 1)
                LEFT JOIN mention_state s ON s.mention_id = m.id
                LEFT JOIN mention_themes t ON t.mention_id = m.id
                WHERE l.type IN ('complaint', 'question', 'purchase_intent')
                  AND m.brand_id = ANY(%s)
                ORDER BY m.posted_at DESC
                LIMIT 1000
                """,
                (focus,),
            )
            rows = cur.fetchall()
            cur.execute(
                "SELECT id, brand_id, name, summary FROM themes WHERE brand_id = ANY(%s) ORDER BY id",
                (focus,),
            )
            themes = [
                {"id": tid, "brand_id": bid, "name": name, "summary": summary}
                for tid, bid, name, summary in cur.fetchall()
            ]
        conn.commit()
    now = datetime.now().astimezone()
    mentions = []
    for (mid, brand_id, platform, surface, url, parent_url, title, author, text, posted_at,
         replied, reply_text, proof, kind, urgency, is_buyer,
         status, snoozed_until, changed_at, is_feedback, draft, theme_id) in rows:
        waited = max(0.0, (now - posted_at).total_seconds() / 3600)
        priority = _URGENCY_POINTS.get(urgency or "low", 20) + (15 if is_buyer else 0) + min(waited / 24, 10)
        mentions.append({
            "id": str(mid),
            "brand_id": brand_id,
            "platform": platform,
            "surface": "owned" if surface == "own" else "earned",
            "url": url,
            "parent_url": parent_url,
            "parent_author": None,
            "parent_title": title,
            "author": author or "unknown",
            "text": text,
            "posted_at": posted_at.isoformat(),
            "like_count": 0,
            "view_count": 0,
            "brand_replied": replied,
            "reply_text": reply_text,
            "proof": "ai_reported" if proof == "grok_bot" else (proof or "none"),
            "type": kind,
            "urgency": urgency or "low",
            "needs_response": replied is not True,
            "priority": round(priority, 1),
            "theme_id": theme_id,
            "draft": draft,
            "status": status or ("handled" if replied else "inbox"),
            "snoozed_until": snoozed_until.isoformat() if snoozed_until else None,
            "status_changed_at": changed_at.isoformat() if changed_at else None,
            "is_feedback": bool(is_feedback),
        })
    return {"me": me, "brands": brands, "themes": themes, "mentions": mentions}


def _desk_id(body: dict) -> int:
    try:
        return int(str(body.get("id", "")))
    except ValueError:
        raise HTTPException(status_code=400, detail="bad id")


@app.post("/api/desk/status")
async def desk_status(request: Request) -> dict:
    me = _session(request)
    body = await request.json()
    mention_id = _desk_id(body)
    status = body.get("status")
    if status not in DESK_STATUSES:
        raise HTTPException(status_code=400, detail="bad status")
    snoozed_until = body.get("snoozed_until") if status == "snoozed" else None
    is_feedback = body.get("is_feedback")
    with _lock:
        conn = db()
        _in_scope(conn, mention_id, me["brands"])
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO mention_state (mention_id, status, snoozed_until, status_changed_at, is_feedback)
                VALUES (%s, %s, %s, now(), COALESCE(%s, false))
                ON CONFLICT (mention_id) DO UPDATE SET
                  status = EXCLUDED.status,
                  snoozed_until = EXCLUDED.snoozed_until,
                  status_changed_at = now(),
                  is_feedback = COALESCE(%s, mention_state.is_feedback)
                """,
                (mention_id, status, snoozed_until, is_feedback, is_feedback),
            )
        conn.commit()
    return {"ok": True}


@app.post("/api/desk/status-batch")
async def desk_status_batch(request: Request) -> dict:
    """Move many messages in one go. Each change carries its own status, so undo can restore a mix."""
    me = _session(request)
    body = await request.json()
    changes = body.get("changes")
    if not isinstance(changes, list) or not 0 < len(changes) <= 1000:
        raise HTTPException(status_code=400, detail="bad changes")
    rows = []
    for change in changes:
        if not isinstance(change, dict):
            raise HTTPException(status_code=400, detail="bad change")
        status = change.get("status")
        if status not in DESK_STATUSES:
            raise HTTPException(status_code=400, detail="bad status")
        snoozed_until = change.get("snoozed_until") if status == "snoozed" else None
        rows.append((_desk_id(change), status, snoozed_until, change.get("is_feedback")))
    ids = [row[0] for row in rows]
    with _lock:
        conn = db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(DISTINCT id) FROM mentions WHERE id = ANY(%s) AND brand_id = ANY(%s)",
                (ids, me["brands"]),
            )
            if cur.fetchone()[0] != len(set(ids)):
                conn.rollback()
                raise HTTPException(status_code=404, detail="not found")
            for mention_id, status, snoozed_until, is_feedback in rows:
                cur.execute(
                    """
                    INSERT INTO mention_state (mention_id, status, snoozed_until, status_changed_at, is_feedback)
                    VALUES (%s, %s, %s, now(), COALESCE(%s, false))
                    ON CONFLICT (mention_id) DO UPDATE SET
                      status = EXCLUDED.status,
                      snoozed_until = EXCLUDED.snoozed_until,
                      status_changed_at = now(),
                      is_feedback = COALESCE(%s, mention_state.is_feedback)
                    """,
                    (mention_id, status, snoozed_until, is_feedback, is_feedback),
                )
        conn.commit()
    return {"ok": True, "moved": len(rows)}


@app.post("/api/desk/draft")
async def desk_draft(request: Request) -> dict:
    me = _session(request)
    body = await request.json()
    mention_id = _desk_id(body)
    draft = str(body.get("draft", ""))[:5000]
    with _lock:
        conn = db()
        _in_scope(conn, mention_id, me["brands"])
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO mention_state (mention_id, draft) VALUES (%s, %s)
                ON CONFLICT (mention_id) DO UPDATE SET draft = EXCLUDED.draft
                """,
                (mention_id, draft),
            )
        conn.commit()
    return {"ok": True}


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
async def api_onboard(request: Request, token: str = "") -> dict:
    _team_or_token(request, token)
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
def publish_demo(queue_id: int, request: Request, token: str = "") -> dict:
    _team_or_token(request, token)
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


def _request_token(request: Request, token: str = "") -> str:
    """The token from an Authorization: Bearer header, then ?token=, then an X-Token header."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    return token or request.headers.get("x-token", "")


def _token_matches(token: str) -> bool:
    """True only when COPILOT_TOKEN is set and the token equals it."""
    load_env()
    required = os.environ.get("COPILOT_TOKEN", "").strip()
    return bool(required) and hmac.compare_digest(token.strip().encode(), required.encode())


def _copilot_allowed(token: str) -> bool:
    """With no COPILOT_TOKEN set, as on localhost, the copilot stays open."""
    load_env()
    if not os.environ.get("COPILOT_TOKEN", "").strip():
        return True
    return _token_matches(token)


def _team_or_token(request: Request, token: str = "") -> None:
    """Lets in the copilot token or a signed-in ReplyInPublic team account. Nothing else.

    No token and no session is a 401. A brand account is a 403. Unlike the copilot,
    a missing COPILOT_TOKEN never opens these routes.
    """
    if _token_matches(_request_token(request, token)):
        return
    if _session(request)["role"] != "rip":
        raise HTTPException(status_code=403, detail="team only")


@app.post("/api/ingest")
async def api_ingest(request: Request, token: str = "") -> dict:
    token = _request_token(request, token)
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
