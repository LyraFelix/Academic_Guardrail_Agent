"""SQLite-backed persistent API response cache for Academic Guardrail.

Caches DOI/title lookup results from Crossref, OpenAlex, and Semantic Scholar
to avoid redundant HTTP requests and to prevent hitting rate-limits (HTTP 429).

Cache location: ~/.cache/academic_guardrail/api_cache.db
Default TTL:    30 days
"""

import os
import json
import time
import sqlite3
import hashlib
import logging
import threading
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "academic_guardrail"
_DEFAULT_DB_NAME = "api_cache.db"
_DEFAULT_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days


class SqliteCache:
    """Thread-safe, async-friendly SQLite persistent cache with TTL expiry.

    Usage::

        cache = SqliteCache()
        val = cache.get("my_key")
        if val is None:
            val = expensive_api_call()
            cache.set("my_key", val)
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        if db_path is None:
            _DEFAULT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            db_path = str(_DEFAULT_CACHE_DIR / _DEFAULT_DB_NAME)
        self.db_path = db_path
        self.ttl_seconds = ttl_seconds
        self._init_db()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_cache (
                    key       TEXT PRIMARY KEY,
                    value     TEXT NOT NULL,
                    expires_at REAL NOT NULL
                )
                """
            )

    @staticmethod
    def make_key(namespace: str, *args: str) -> str:
        """Create a stable hash key from a namespace and one or more string args."""
        raw = namespace + "|" + "|".join(a.lower().strip() for a in args if a)
        return hashlib.sha256(raw.encode()).hexdigest()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[Any]:
        """Return the cached value or None if missing / expired."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT value, expires_at FROM api_cache WHERE key = ?",
                    (key,),
                ).fetchone()
            if row is None:
                return None
            value_json, expires_at = row
            if time.time() > expires_at:
                self.delete(key)
                return None
            return json.loads(value_json)
        except Exception as exc:
            logger.debug("Cache read error for key %s: %s", key, exc)
            return None

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Store a JSON-serialisable value in the cache."""
        ttl = ttl_seconds if ttl_seconds is not None else self.ttl_seconds
        expires_at = time.time() + ttl
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO api_cache (key, value, expires_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                                   expires_at = excluded.expires_at
                    """,
                    (key, json.dumps(value, ensure_ascii=False), expires_at),
                )
        except Exception as exc:
            logger.debug("Cache write error for key %s: %s", key, exc)

    def delete(self, key: str) -> None:
        """Remove a single entry."""
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM api_cache WHERE key = ?", (key,))
        except Exception:
            pass

    def purge_expired(self) -> int:
        """Delete all expired entries and return count removed."""
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "DELETE FROM api_cache WHERE expires_at < ?", (time.time(),)
                )
                return cur.rowcount
        except Exception:
            return 0

    def clear(self) -> None:
        """Wipe the entire cache table (useful for testing)."""
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM api_cache")
        except Exception:
            pass

    def stats(self) -> dict:
        """Return a dict with total entries and expired entries counts."""
        try:
            with self._connect() as conn:
                total = conn.execute("SELECT COUNT(*) FROM api_cache").fetchone()[0]
                expired = conn.execute(
                    "SELECT COUNT(*) FROM api_cache WHERE expires_at < ?", (time.time(),)
                ).fetchone()[0]
            return {"total": total, "expired": expired, "valid": total - expired}
        except Exception:
            return {"total": 0, "expired": 0, "valid": 0}


# Module-level singleton — shared across all providers in the same process.
_global_cache: Optional[SqliteCache] = None
_cache_lock = threading.Lock()


def get_cache() -> SqliteCache:
    """Return the process-wide singleton cache, creating it on first call (thread-safe)."""
    global _global_cache
    if _global_cache is None:
        with _cache_lock:
            if _global_cache is None:
                _global_cache = SqliteCache()
    return _global_cache
