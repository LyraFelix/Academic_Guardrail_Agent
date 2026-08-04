"""Offline Retraction Watch SQLite Database Provider for zero-latency, rate-limit-free verification."""

import os
import sqlite3
from typing import Optional, Dict, Any


class OfflineRetractionDB:
    """High-performance SQLite database wrapper for Retraction Watch offline data."""

    def __init__(self, db_path: str = "retraction_watch.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS retractions (
                doi TEXT PRIMARY KEY,
                title TEXT,
                journal TEXT,
                retraction_date TEXT,
                reason TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_doi ON retractions(doi)")
        conn.commit()
        conn.close()

    def seed_known_retractions(self, records: list):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        for r in records:
            cursor.execute("""
                INSERT OR REPLACE INTO retractions (doi, title, journal, retraction_date, reason)
                VALUES (?, ?, ?, ?, ?)
            """, (r["doi"].lower().strip(), r.get("title", ""), r.get("journal", ""), r.get("date", ""), r.get("reason", "Retracted")))
        conn.commit()
        conn.close()

    def check_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        clean_doi = doi.lower().replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT doi, title, journal, retraction_date, reason FROM retractions WHERE doi = ?", (clean_doi,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "doi": row[0],
                "title": row[1],
                "journal": row[2],
                "retraction_date": row[3],
                "reason": row[4],
                "is_retracted": True
            }
        return None
