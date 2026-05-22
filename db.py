"""
db.py
-----
PostgreSQL connection and query execution for the AI Job Market Agent.
Read-only access only — the DB user should have SELECT permissions only.
"""

import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    """
    Returns a psycopg2 connection using credentials from .env file.
    """
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "ai_job_market"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )


def run_query(sql: str) -> tuple[list[dict], str | None]:
    """
    Executes a read-only SQL query and returns results as a list of dicts.

    Returns:
        (rows, error)
        - rows: list of dicts (column name -> value), empty list if no results
        - error: error message string if query failed, None if successful
    """
    # Safety check — block any non-SELECT statements
    normalized = sql.strip().lower()
    if not normalized.startswith(("select", "with")):
        return [], "Blocked: only SELECT and WITH queries are permitted."

    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            rows = [dict(row) for row in cur.fetchall()]
            return rows, None

    except Exception as e:
        return [], str(e)

    finally:
        if conn:
            conn.close()


def test_connection() -> bool:
    """
    Quick connectivity test. Prints success or error message.
    Returns True if connection succeeded, False otherwise.
    """
    try:
        conn = get_connection()
        conn.close()
        print("✅ Database connection successful.")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False


if __name__ == "__main__":
    test_connection()