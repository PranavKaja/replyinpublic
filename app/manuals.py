"""Download public warranty and FAQ pages, chunk them, and store Gemini embeddings."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from app.db import ROOT, connect, load_env

PAGES = [
    ("kitchenaid", "KitchenAid warranty", "https://www.kitchenaid.com/countertop-appliances/customer-care/warranty"),
    ("nespresso", "Nespresso warranty FAQ", "https://www.contact.nespresso.com/faq-3/us/en/?query=warranty"),
    ("breville", "Breville limited warranty", "https://www.breville.com/en-us/support/warranty"),
    ("instant", "Instant Pot product warranties", "https://instantpot.com/pages/product-warranties"),
    ("ninja", "Ninja 5 year limited warranty", "https://support.ninjakitchen.com/hc/en-us/articles/4402874054546-Ninja-5-Year-Limited-Warranty"),
]
MANUALS = ROOT / "manuals"
MODEL = "gemini-embedding-001"
DIM = 768


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            text = " ".join(data.split())
            if text:
                self.parts.append(text)


def page_text(url: str) -> str:
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
    })
    with urllib.request.urlopen(request, timeout=40) as response:
        raw = response.read().decode("utf-8", "replace")
    parser = TextExtractor()
    parser.feed(raw)
    text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    return text


def chunks(text: str, size: int = 700) -> list[str]:
    words = text.split()
    out = []
    buf: list[str] = []
    length = 0
    for word in words:
        if length + len(word) + 1 > size and buf:
            out.append(" ".join(buf))
            buf = []
            length = 0
        buf.append(word)
        length += len(word) + 1
    if buf:
        out.append(" ".join(buf))
    return [part for part in out if len(part) > 80]


def embed(key: str, text: str) -> list[float] | None:
    body = json.dumps({
        "content": {"parts": [{"text": text[:6000]}]},
        "outputDimensionality": DIM,
    }).encode()
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:embedContent?key={key}",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.load(response)
                break
        except urllib.error.HTTPError as exc:
            if exc.code == 402:
                return None
            if exc.code in (403, 429, 503) and attempt < 4:
                import time
                time.sleep(4 * (attempt + 1))
                continue
            raise
    else:
        return None
    values = payload["embedding"]["values"]
    if len(values) != DIM:
        raise RuntimeError(f"embedding length {len(values)}")
    return values


def ensure(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS kb_docs (
              id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
              brand_id text NOT NULL REFERENCES brands (id),
              title text NOT NULL,
              source_url text NOT NULL,
              fetched_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS kb_chunks (
              id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
              doc_id bigint NOT NULL REFERENCES kb_docs (id),
              brand_id text NOT NULL,
              text text NOT NULL,
              source_url text NOT NULL,
              embedding vector({DIM})
            )
            """
        )
        cur.execute("ALTER TABLE kb_chunks ALTER COLUMN embedding DROP NOT NULL")
    conn.commit()


def main() -> None:
    load_env()
    key = os.environ["GEMINI_API_KEY"]
    MANUALS.mkdir(exist_ok=True)
    with connect() as conn:
        ensure(conn)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM kb_chunks")
            cur.execute("DELETE FROM kb_docs")
        conn.commit()
        for brand_id, title, url in PAGES:
            try:
                text = page_text(url)
            except Exception as exc:
                print(f"{brand_id}: download failed {exc}", flush=True)
                continue
            if len(text) < 400:
                print(f"{brand_id}: page too thin ({len(text)} chars)", flush=True)
                continue
            path = MANUALS / f"{brand_id}.txt"
            path.write_text(url + "\n\n" + text, encoding="utf-8")
            parts = chunks(text)
            print(f"{brand_id}: {len(text)} chars, {len(parts)} chunks", flush=True)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO kb_docs (brand_id, title, source_url)
                    VALUES (%s, %s, %s)
                    RETURNING id
                    """,
                    (brand_id, title, url),
                )
                doc_id = cur.fetchone()[0]
            stored = 0
            skipped_embed = False
            for part in parts:
                vector = embed(key, part)
                if vector is None:
                    skipped_embed = True
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO kb_chunks (doc_id, brand_id, text, source_url, embedding)
                            VALUES (%s, %s, %s, %s, NULL)
                            """,
                            (doc_id, brand_id, part, url),
                        )
                else:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO kb_chunks (doc_id, brand_id, text, source_url, embedding)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            (doc_id, brand_id, part, url, str(vector)),
                        )
                stored += 1
            conn.commit()
            print(f"{brand_id}: stored {stored} embed={'no' if skipped_embed else 'yes'}", flush=True)


if __name__ == "__main__":
    import os
    main()
