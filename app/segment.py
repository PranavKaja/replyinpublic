"""Segment comments. Obvious noise is labeled here and stays off the dashboard.

Gemini labels the rest when the API key is present. A quota error stops the model
pass and leaves the rule labels in place.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

from app.db import connect, load_env

REACTIONS = {
    "lol", "lmao", "lmfao", "haha", "hahaha", "hehe", "wow", "omg", "nice", "cool",
    "first", "yum", "yummy", "damn", "du", "duu", "ha", "yes", "no", "ok", "okay",
    "thanks", "thank you", "thx", "love", "love it", "so good", "fire", "goat",
    "same", "bro", "dude", "nah", "yep", "ya", "yeah", "na", "nope", "hi", "hey",
    "hello", "gg", "wp", "omfg", "lmao", "rofl",
}
MODELS = (
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash-lite",
)
BATCH = 12
FOCUS = ("instant", "kitchenaid", "traeger", "ninja", "delonghi")


def is_noise(text: str) -> bool:
    raw = text or ""
    letters_only = re.sub(r"[^a-z]", "", raw.lower())
    if re.search(r"(.)\1{3,}", letters_only):
        collapsed = re.sub(r"(.)\1{2,}", r"\1", letters_only)
        if len(collapsed) <= 4:
            return True
    cleaned = re.sub(r"https?://\S+", " ", raw.lower())
    cleaned = re.sub(r"[^a-z0-9\s']", " ", cleaned)
    cleaned = re.sub(r"(.)\1{2,}", r"\1\1", cleaned)
    words = [word for word in cleaned.split() if word]
    if not words:
        return True
    if len(words) == 1 and len(set(words[0])) == 1:
        return True
    joined = " ".join(words)
    if joined in REACTIONS or (len(words) <= 3 and all(word in REACTIONS for word in words)):
        return True
    if len(re.sub(r"[^a-z]", "", joined)) < 3:
        return True
    return False


def ensure_labels(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("ALTER TABLE labels ADD COLUMN IF NOT EXISTS topic text")
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS labels_mention_key
            ON labels (mention_id, posted_at)
            """
        )
    conn.commit()


def save_label(conn, mention_id: int, posted_at, label: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO labels (
              mention_id, posted_at, type, sentiment, urgency, is_buyer,
              relevant, model, labeled_at, topic
            ) VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, now(), %s
            )
            ON CONFLICT (mention_id, posted_at) DO UPDATE SET
              type = EXCLUDED.type,
              sentiment = EXCLUDED.sentiment,
              urgency = EXCLUDED.urgency,
              is_buyer = EXCLUDED.is_buyer,
              relevant = EXCLUDED.relevant,
              model = EXCLUDED.model,
              labeled_at = now(),
              topic = EXCLUDED.topic
            """,
            (
                mention_id,
                posted_at,
                label.get("type"),
                label.get("sentiment"),
                label.get("urgency"),
                label.get("is_buyer"),
                label.get("relevant"),
                label.get("model"),
                label.get("topic"),
            ),
        )


def label_rules(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.id, m.posted_at, m.text
            FROM mentions m
            WHERE NOT EXISTS (
              SELECT 1 FROM labels l
              WHERE l.mention_id = m.id AND l.posted_at = m.posted_at
            )
            """
        )
        rows = cur.fetchall()
    kept = 0
    for mention_id, posted_at, text in rows:
        if not is_noise(text or ""):
            continue
        save_label(conn, mention_id, posted_at, {
            "type": "noise",
            "sentiment": "neutral",
            "urgency": "low",
            "is_buyer": False,
            "relevant": False,
            "model": "rules",
            "topic": None,
        })
        kept += 1
    conn.commit()
    return kept


def label_gemini(conn, limit_batches: int = 24) -> tuple[int, str]:
    load_env()
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return 0, "GEMINI_API_KEY missing"
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.id, m.posted_at, m.text
            FROM mentions m
            JOIN brands b ON b.id = m.brand_id
            WHERE b.id = ANY(%s)
              AND NOT EXISTS (
                SELECT 1 FROM labels l
                WHERE l.mention_id = m.id AND l.posted_at = m.posted_at
              )
            ORDER BY m.posted_at DESC
            LIMIT %s
            """,
            (list(FOCUS), limit_batches * BATCH),
        )
        rows = cur.fetchall()
    labeled = 0
    note = "ok"
    for start in range(0, len(rows), BATCH):
        chunk = rows[start:start + BATCH]
        try:
            found, model = ask_gemini(key, chunk)
        except QuotaError as exc:
            note = str(exc)
            break
        except Exception as exc:
            note = f"{exc.__class__.__name__}: {exc}"
            break
        by_id = {str(mention_id): (mention_id, posted_at) for mention_id, posted_at, _ in chunk}
        for item in found:
            pair = by_id.get(str(item.get("mention_id")))
            if not pair:
                continue
            kind = item.get("type") if item.get("type") in {
                "question", "complaint", "praise", "purchase_intent", "noise"
            } else "noise"
            relevant = kind != "noise"
            save_label(conn, pair[0], pair[1], {
                "type": kind,
                "sentiment": item.get("sentiment") if item.get("sentiment") in {
                    "negative", "neutral", "positive"
                } else "neutral",
                "urgency": item.get("urgency") if item.get("urgency") in {
                    "low", "medium", "high"
                } else "low",
                "is_buyer": kind == "purchase_intent",
                "relevant": relevant,
                "model": model,
                "topic": (item.get("topic") or "")[:80] or None,
            })
            labeled += 1
        conn.commit()
        print(f"gemini {model}: labeled {labeled}", flush=True)
    return labeled, note


class QuotaError(RuntimeError):
    pass


def ask_gemini(key: str, chunk: list) -> tuple[list, str]:
    lines = []
    for mention_id, _posted, text in chunk:
        flat = " ".join((text or "").split())
        lines.append(f"{mention_id}\t{flat[:500]}")
    prompt = (
        "Classify each public comment about a kitchen brand. "
        "Return a JSON array only. Each object has mention_id, type, sentiment, urgency, topic. "
        "type is question, complaint, praise, purchase_intent, or noise. "
        "noise means jokes, spam, emoji, empty reactions, or chatter that is not about the product. "
        "sentiment is negative, neutral, or positive. urgency is low, medium, or high. "
        "topic is 1 to 3 words or an empty string. Echo mention_id exactly.\n"
        + "\n".join(lines)
    )
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
        try:
            with urllib.request.urlopen(request, timeout=150) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:180]
            last = f"{model} HTTP {exc.code} {detail}"
            if exc.code in (429, 404, 400):
                if exc.code == 429 and model == MODELS[-1]:
                    raise QuotaError(last)
                continue
            raise
        except TimeoutError:
            last = f"{model} timeout"
            continue
        text = ""
        for candidate in payload.get("candidates") or []:
            for part in (candidate.get("content") or {}).get("parts") or []:
                text += part.get("text") or ""
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            parsed = parsed.get("labels") or parsed.get("comments") or []
        if not isinstance(parsed, list):
            raise RuntimeError(f"{model} returned {type(parsed).__name__}")
        return parsed, model
    raise QuotaError(last)


def self_check() -> None:
    assert is_noise("Duuuuu.")
    assert is_noise("lol")
    assert is_noise("🔥🔥")
    assert not is_noise("Ninja does in fact leave the frozen layer at the bottom. Very annoying")
    assert not is_noise("The pod leaks after one week")
    print("noise checks ok")


def main() -> None:
    self_check()
    load_env()
    with connect() as conn:
        ensure_labels(conn)
        ruled = label_rules(conn)
        print(f"rule noise {ruled}", flush=True)
        labeled, note = label_gemini(conn)
        print(f"gemini labeled {labeled} note {note}", flush=True)


if __name__ == "__main__":
    main()
