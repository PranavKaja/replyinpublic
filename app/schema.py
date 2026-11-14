"""Apply schema.sql, then try the labels foreign key."""

import re

from app.db import ROOT, connect

SCHEMA = ROOT / "schema.sql"


def sql_statements() -> list[str]:
    text = SCHEMA.read_text(encoding="utf-8").replace("\r\n", "\n")
    statements = []
    for part in re.split(r";\s*", text):
        body = "\n".join(
            line for line in part.split("\n") if line.strip() and not line.strip().startswith("--")
        ).strip()
        if body:
            statements.append(body)
    return statements


def apply() -> None:
    statements = sql_statements()
    with connect() as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
                print("timescaledb extension ready")
            except Exception as exc:
                print(f"timescaledb extension statement failed: {exc}")
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                print("pgvector extension ready")
            except Exception as exc:
                print(f"pgvector not enabled on this server: {exc}")
            for statement in statements:
                cur.execute(statement)
            _labels_foreign_key(cur)
    print("schema applied")


def _labels_foreign_key(cur) -> None:
    """Timescale often rejects a foreign key into a hypertable. mention_id stays indexed either way."""
    try:
        cur.execute("ALTER TABLE labels DROP CONSTRAINT IF EXISTS labels_mention_fk")
        cur.execute(
            """
            ALTER TABLE labels
              ADD CONSTRAINT labels_mention_fk
              FOREIGN KEY (mention_id, posted_at)
              REFERENCES mentions (id, posted_at)
            """
        )
        print("labels foreign key created")
    except Exception as exc:
        print(f"labels foreign key skipped: {exc.__class__.__name__}: {exc}")
        print("mention_id stays indexed on labels_mention_id_idx")


if __name__ == "__main__":
    apply()
