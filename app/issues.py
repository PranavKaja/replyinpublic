"""Group each focus brand's complaints, questions and buyer comments into named issues.

The first run for a brand asks Gemini to name 5 to 8 issues and place each comment.
Later runs only place new comments into the issues that already exist.
Run: python -m app.issues
"""

import json
import os
import time
import urllib.error
import urllib.request

from app.db import ROOT, connect, load_env

MODELS = ("gemini-3.5-flash", "gemini-3.5-flash-lite")
CHUNK = 80

TABLES = (
    """
    CREATE TABLE IF NOT EXISTS themes (
      id text PRIMARY KEY,
      brand_id text NOT NULL,
      name text NOT NULL,
      summary text NOT NULL DEFAULT '',
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mention_themes (
      mention_id bigint PRIMARY KEY,
      theme_id text,
      placed_at timestamptz NOT NULL DEFAULT now()
    )
    """,
)


def ensure_tables(conn) -> None:
    with conn.cursor() as cur:
        for statement in TABLES:
            cur.execute(statement)
    conn.commit()


def ask(key: str, prompt: str) -> dict:
    last = "no model"
    for model in MODELS:
        body = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        }).encode()
        request = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=240) as response:
                    payload = json.load(response)
            except urllib.error.HTTPError as exc:
                last = f"{model} HTTP {exc.code} {exc.read().decode('utf-8', 'replace')[:160]}"
                if exc.code in (429, 503) and attempt < 3:
                    time.sleep(10)
                    continue
                break
            except TimeoutError:
                last = f"{model} timeout"
                break
            text = ""
            for candidate in payload.get("candidates") or []:
                for part in (candidate.get("content") or {}).get("parts") or []:
                    text += part.get("text") or ""
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                last = f"{model} returned text that is not JSON"
                break
            if isinstance(parsed, dict):
                return parsed
            last = f"{model} returned {type(parsed).__name__}"
            break
    raise RuntimeError(last)


def lines_for(rows: list) -> str:
    return "\n".join(f"{mid}\t{kind}\t{' '.join((text or '').split())[:300]}" for mid, kind, text in rows)


def unplaced(conn, brand: str) -> list:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.id, l.type, m.text
            FROM mentions m
            JOIN LATERAL (
              SELECT type FROM labels
              WHERE mention_id = m.id AND posted_at = m.posted_at
              ORDER BY labeled_at DESC NULLS LAST LIMIT 1
            ) l ON true
            LEFT JOIN mention_themes t ON t.mention_id = m.id
            WHERE m.brand_id = %s
              AND l.type IN ('complaint', 'question', 'purchase_intent')
              AND t.mention_id IS NULL
            ORDER BY m.posted_at DESC
            """,
            (brand,),
        )
        return cur.fetchall()


def save(conn, brand: str, rows: list, themes: list, placements: list) -> int:
    """themes is the brand's full ordered id list. placements is [{id, issue}]."""
    known = {mid for mid, _kind, _text in rows}
    placed = 0
    with conn.cursor() as cur:
        seen = set()
        for item in placements:
            try:
                mid = int(item.get("id"))
                index = int(item.get("issue"))
            except (TypeError, ValueError, AttributeError):
                continue
            if mid not in known or mid in seen:
                continue
            seen.add(mid)
            theme_id = themes[index] if 0 <= index < len(themes) else None
            cur.execute(
                """
                INSERT INTO mention_themes (mention_id, theme_id) VALUES (%s, %s)
                ON CONFLICT (mention_id) DO NOTHING
                """,
                (mid, theme_id),
            )
            placed += theme_id is not None
        # A comment the model skipped is stored with no issue so it is not sent again.
        for mid in known - seen:
            cur.execute(
                "INSERT INTO mention_themes (mention_id, theme_id) VALUES (%s, NULL) ON CONFLICT DO NOTHING",
                (mid,),
            )
    conn.commit()
    return placed


def group_brand(conn, key: str, brand: str, brand_name: str) -> str:
    rows = unplaced(conn, brand)
    if not rows:
        return "nothing new"
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, summary FROM themes WHERE brand_id = %s ORDER BY id", (brand,))
        existing = cur.fetchall()
    if not existing:
        prompt = (
            f"These are public comments about {brand_name} products that the brand has not answered. "
            "Each line is id, type, text, separated by tabs. Comments may be in any language.\n"
            "Name 6 to 8 issues that together cover most of these comments: the complaints, "
            "the questions people keep asking, and the things buyers want to know before buying. "
            "Keep each issue broad enough to hold many comments. "
            "Name each issue in plain English, 3 to 6 words, the way a customer would say it, "
            "for example 'Pods have less coffee' or 'Which model should I buy'. No brand name in the name. "
            "Write a one sentence summary of each issue using only what the comments say.\n"
            'Return JSON only: {"issues": [{"name": "", "summary": ""}]}\n'
            + lines_for(rows[:400])
        )
        answer = ask(key, prompt)
        issues = [i for i in (answer.get("issues") or []) if isinstance(i, dict) and i.get("name")][:8]
        if not issues:
            raise RuntimeError(f"{brand}: no issues returned")
        with conn.cursor() as cur:
            for index, issue in enumerate(issues):
                cur.execute(
                    """
                    INSERT INTO themes (id, brand_id, name, summary) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (f"{brand}:{index}", brand, str(issue["name"])[:80], str(issue.get("summary") or "")[:400]),
                )
        conn.commit()
        existing = [(f"{brand}:{i}", issue["name"], issue.get("summary") or "") for i, issue in enumerate(issues)]
    listing = "\n".join(f"{i}\t{name}\t{summary}" for i, (_id, name, summary) in enumerate(existing))
    placed = 0
    for start in range(0, len(rows), CHUNK):
        chunk = rows[start:start + CHUNK]
        prompt = (
            f"These are public comments about {brand_name} products. "
            "Each comment line is id, type, text, separated by tabs. Comments may be in any language.\n"
            "Place each comment in the existing issue below that fits it best, by its number. "
            "Use -1 only for a comment that fits none of them, including spam and deal posts. "
            "Do not invent issues. Return every id.\n"
            'Return JSON only: {"assign": [{"id": 0, "issue": 0}]}\n'
            "Issues:\n" + listing + "\nComments:\n" + lines_for(chunk)
        )
        answer = ask(key, prompt)
        placed += save(conn, brand, chunk, [tid for tid, _n, _s in existing], answer.get("assign") or [])
    return f"{len(rows)} read, {placed} placed, {len(existing)} issues"


def main() -> None:
    load_env()
    key = os.environ["GEMINI_API_KEY"]
    focus = json.loads((ROOT / "focus.json").read_text(encoding="utf-8"))["brands"]
    with connect() as conn:
        ensure_tables(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM brands WHERE id = ANY(%s)", (focus,))
            names = dict(cur.fetchall())
        for brand in focus:
            try:
                print(brand, group_brand(conn, key, brand, names.get(brand, brand)), flush=True)
            except Exception as exc:  # one brand failing must not stop the rest
                conn.rollback()
                print(brand, "failed:", exc, flush=True)


if __name__ == "__main__":
    main()
