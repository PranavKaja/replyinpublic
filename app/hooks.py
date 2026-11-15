"""Phase 1 hooks so later phases (scores, desk, concierge) can plug in.

See 12-Overheard/docs/LATER-PHASES.md in the Career Hub for the product map.
"""

from __future__ import annotations

import json
import re

MIGRATIONS = [
    """
    ALTER TABLE brands
      ADD COLUMN IF NOT EXISTS support_contact text,
      ADD COLUMN IF NOT EXISTS reply_sla_hours integer NOT NULL DEFAULT 48
    """,
    """
    ALTER TABLE mentions
      ADD COLUMN IF NOT EXISTS case_id text,
      ADD COLUMN IF NOT EXISTS brand_reply_at timestamptz,
      ADD COLUMN IF NOT EXISTS brand_reply_author text
    """,
    """
    CREATE INDEX IF NOT EXISTS mentions_case_id_idx
      ON mentions (case_id)
      WHERE case_id IS NOT NULL
    """,
    """
    CREATE TABLE IF NOT EXISTS reply_drafts (
      mention_id bigint NOT NULL,
      posted_at timestamptz NOT NULL,
      draft_text text NOT NULL,
      final_text text,
      status text NOT NULL DEFAULT 'suggested',
      source_passages jsonb,
      model text,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (mention_id, posted_at)
    )
    """,
]


def case_id_for(brand_id: str, mention_id: int) -> str:
    letters = re.sub(r"[^a-z]", "", brand_id.lower())[:4].upper() or "BRND"
    return f"RIP-{letters}-{mention_id:06d}"


def apply_phase_hooks(conn) -> None:
    with conn.cursor() as cur:
        for statement in MIGRATIONS:
            cur.execute(statement)
        cur.execute(
            """
            SELECT m.id, m.brand_id
            FROM mentions m
            WHERE m.case_id IS NULL
            ORDER BY m.id
            """
        )
        for mention_id, brand_id in cur.fetchall():
            code = case_id_for(brand_id, mention_id)
            cur.execute(
                "UPDATE mentions SET case_id = %s WHERE id = %s AND case_id IS NULL",
                (code, mention_id),
            )
    conn.commit()


def stamp_case_id(cur, mention_id: int, brand_id: str) -> str:
    code = case_id_for(brand_id, mention_id)
    cur.execute(
        "UPDATE mentions SET case_id = %s WHERE id = %s AND case_id IS NULL",
        (code, mention_id),
    )
    return code


def save_reply_draft(
    conn,
    mention_id: int,
    posted_at,
    draft_text: str,
    passages: list,
    model: str = "gemini-3.5-flash-lite",
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO reply_drafts (
              mention_id, posted_at, draft_text, source_passages, model, status
            ) VALUES (%s, %s, %s, %s::jsonb, %s, 'suggested')
            ON CONFLICT (mention_id, posted_at) DO UPDATE SET
              draft_text = EXCLUDED.draft_text,
              source_passages = EXCLUDED.source_passages,
              model = EXCLUDED.model,
              status = CASE
                WHEN reply_drafts.status IN ('approved', 'edited') THEN reply_drafts.status
                ELSE 'suggested'
              END,
              updated_at = now()
            """,
            (mention_id, posted_at, draft_text, json.dumps(passages, ensure_ascii=False), model),
        )
    conn.commit()


def update_draft_status(
    conn,
    mention_id: int,
    posted_at,
    status: str,
    final_text: str | None,
) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE reply_drafts
            SET status = %s,
                final_text = COALESCE(%s, final_text, draft_text),
                updated_at = now()
            WHERE mention_id = %s AND posted_at = %s
            RETURNING draft_text
            """,
            (status, final_text, mention_id, posted_at),
        )
        row = cur.fetchone()
    if row:
        conn.commit()
        return True
    conn.rollback()
    return False