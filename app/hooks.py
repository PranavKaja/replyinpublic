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
    """
    CREATE TABLE IF NOT EXISTS mention_state (
      mention_id bigint PRIMARY KEY,
      status text NOT NULL DEFAULT 'inbox',
      snoozed_until timestamptz,
      status_changed_at timestamptz,
      is_feedback boolean NOT NULL DEFAULT false,
      draft text
    )
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
    """
    ALTER TABLE reply_drafts
      ADD COLUMN IF NOT EXISTS publish_channel text DEFAULT 'public',
      ADD COLUMN IF NOT EXISTS publish_status text DEFAULT 'none'
    """,
    """
    ALTER TABLE brands
      ADD COLUMN IF NOT EXISTS onboarding_status text DEFAULT 'demo'
    """,
    """
    CREATE TABLE IF NOT EXISTS brand_connections (
      brand_id text NOT NULL REFERENCES brands (id),
      platform text NOT NULL,
      status text NOT NULL DEFAULT 'pilot_pending',
      note text,
      updated_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (brand_id, platform)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS onboarding_leads (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      company_name text NOT NULL,
      contact_name text NOT NULL,
      contact_email text NOT NULL,
      brand_slug text,
      kb_url text,
      platforms text[] NOT NULL DEFAULT '{}',
      status text NOT NULL DEFAULT 'new',
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS publish_queue (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      mention_id bigint NOT NULL,
      posted_at timestamptz NOT NULL,
      case_id text,
      channel text NOT NULL DEFAULT 'public',
      body text NOT NULL,
      status text NOT NULL DEFAULT 'queued',
      queued_at timestamptz NOT NULL DEFAULT now(),
      posted_demo_at timestamptz
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS publish_queue_status_idx
      ON publish_queue (status, queued_at DESC)
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
    publish_channel: str = "public",
) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE reply_drafts
            SET status = %s,
                final_text = COALESCE(%s, final_text, draft_text),
                publish_channel = %s,
                publish_status = CASE
                  WHEN %s IN ('approved', 'edited') THEN 'queued'
                  WHEN %s = 'rejected' THEN 'skipped'
                  ELSE publish_status
                END,
                updated_at = now()
            WHERE mention_id = %s AND posted_at = %s
            RETURNING COALESCE(final_text, draft_text)
            """,
            (
                status,
                final_text,
                publish_channel,
                status,
                status,
                mention_id,
                posted_at,
            ),
        )
        row = cur.fetchone()
        if row and status in {"approved", "edited"}:
            text = row[0]
            cur.execute(
                """
                SELECT case_id FROM mentions
                WHERE id = %s AND posted_at = %s
                """,
                (mention_id, posted_at),
            )
            case_row = cur.fetchone()
            case_id = case_row[0] if case_row else None
            cur.execute(
                """
                INSERT INTO publish_queue (mention_id, posted_at, case_id, channel, body, status)
                VALUES (%s, %s, %s, %s, %s, 'queued')
                """,
                (mention_id, posted_at, case_id, publish_channel, text),
            )
    if row:
        conn.commit()
        return True
    conn.rollback()
    return False


def mark_publish_demo(conn, queue_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE publish_queue
            SET status = 'posted_demo', posted_demo_at = now()
            WHERE id = %s AND status = 'queued'
            RETURNING mention_id, posted_at
            """,
            (queue_id,),
        )
        row = cur.fetchone()
        if row:
            mention_id, posted_at = row
            cur.execute(
                """
                UPDATE reply_drafts
                SET publish_status = 'posted_demo', updated_at = now()
                WHERE mention_id = %s AND posted_at = %s
                """,
                (mention_id, posted_at),
            )
    if row:
        conn.commit()
        return True
    conn.rollback()
    return False