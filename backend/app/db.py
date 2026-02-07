"""
PostgreSQL connection for the backend.
Uses DATABASE_URL from environment (e.g. Supabase connection string).
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

def get_connection():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg2.connect(url)

@contextmanager
def get_cursor(commit=False):
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
            if commit:
                conn.commit()
    finally:
        conn.close()
