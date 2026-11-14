"""Database connection. The URL stays in .env."""

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def load_env() -> None:
    load_dotenv(ROOT / ".env")


def database_url() -> str:
    load_env()
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise SystemExit("DATABASE_URL is missing from .env. Add the Tiger Data connection string and run again.")
    return url


def connect() -> psycopg.Connection:
    return psycopg.connect(database_url())
