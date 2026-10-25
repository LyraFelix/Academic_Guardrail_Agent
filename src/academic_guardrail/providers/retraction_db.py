"""Offline Retraction Watch Database Provider.

Provides instant (<0.1ms) zero-network-latency DOI retraction checks using
an in-memory normalized HashSet index backed by SQLite storage.

⚠️  IMPORTANT — About the built-in seed data:
    The three records below are well-documented, publicly verifiable historic
    retraction cases included **only as demo fixtures** to make offline checks
    functional out-of-the-box.

    For production use, supply a real Retraction Watch CSV export via:
        export RETRACTION_DB_PATH=/path/to/retraction_watch.db

    The built-in seed list is NOT a substitute for the full Retraction Watch
    database and covers only a tiny fraction of real retractions.
"""

import os
import sqlite3
import logging
from typing import Optional, Dict, Any, List
from academic_guardrail.core.ref_resolver import ReferenceResolver
from academic_guardrail.core.exceptions import ProviderError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Demo Fixtures — 3 fully verifiable, widely-cited retraction cases.
# Sources: Retraction Watch / PubMed / Nature News.
# DO NOT add records unless the DOI and title can be cross-checked in
# PubMed/Crossref. Inaccurate retraction data is worse than no data.
# ---------------------------------------------------------------------------
KNOWN_RETRACTION_SEEDS: List[Dict[str, Any]] = [
    {
        # Hwang Woo-suk stem cell fraud — Science, 2005
        # Original DOI: 10.1126/science.1112286 | Retraction Notice DOI: 10.1126/science.1124926
        "doi": "10.1126/science.1112286",
        "title": "Patient-Specific Embryonic Stem Cells Derived from Human SCNT Blastocysts",
        "reason": "Data Fabrication — non-existent patient-specific cell lines",
        "journal": "Science",
        "date": "2006-01-12"
    },
    {
        # Andrew Wakefield MMR-autism fraud — The Lancet, 1998
        # Original DOI: 10.1016/S0140-6736(97)11096-0 | Retraction Notice DOI: 10.1016/S0140-6736(10)60175-4
        "doi": "10.1016/S0140-6736(97)11096-0",
        "title": "Ileal-lymphoid-nodular hyperplasia, non-specific colitis, and pervasive developmental disorder in children",
        "reason": "Ethical violation & falsified autism-MMR vaccine link",
        "journal": "The Lancet",
        "date": "2010-02-02"
    },
    {
        # STAP cells (Haruko Obokata et al.) — Nature, 2014
        # Original DOI: 10.1038/nature12968 | Retraction Notice DOI: 10.1038/nature13598
        "doi": "10.1038/nature12968",
        "title": "Stimulus-triggered fate conversion of somatic cells into pluripotency",
        "reason": "Data fabrication and image manipulation",
        "journal": "Nature",
        "date": "2014-07-02"
    },
]


class OfflineRetractionDB:
    """Local SQLite lookup with a small bundled historical demo index."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.environ.get("RETRACTION_DB_PATH", ":memory:")
        self._retracted_set = set()
        self._records_map = {}
        self._conn = None
        self._initialization_error = None
        self._init_db()

    def _init_db(self):
        try:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = self._conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS retractions (
                    doi TEXT PRIMARY KEY,
                    title TEXT,
                    journal TEXT,
                    retraction_date TEXT,
                    reason TEXT
                )
            """)
            self._conn.commit()

            # Seed standard known retractions
            self.seed_known_retractions(KNOWN_RETRACTION_SEEDS)
        except Exception as e:
            logger.warning(
                "[academic_guardrail] Failed to initialize SQLite RetractionDB (%s), "
                "lookups will report unavailability.", e
            )
            self._initialization_error = e
            self.close()

    def seed_known_retractions(self, records: List[Dict[str, Any]]):
        """Add missing demo records without overwriting a user's curated database."""
        cursor = self._conn.cursor() if self._conn else None
        for record in records:
            doi = ReferenceResolver.normalize_doi(record.get("doi"))
            if not doi:
                continue
            stored = dict(record)
            if cursor:
                cursor.execute(
                    "INSERT OR IGNORE INTO retractions (doi, title, journal, retraction_date, reason) VALUES (?, ?, ?, ?, ?)",
                    (doi, record.get("title", ""), record.get("journal", ""), record.get("date", ""), record.get("reason", "")))
                row = cursor.execute(
                    "SELECT doi, title, journal, retraction_date, reason FROM retractions WHERE doi = ?", (doi,)).fetchone()
                stored = dict(zip(("doi", "title", "journal", "date", "reason"), row))
            self._retracted_set.add(doi)
            self._records_map[doi] = stored
        if self._conn:
            self._conn.commit()

    def check_doi(self, doi_str: str) -> Optional[Dict[str, Any]]:
        """Return a matching record; raise on storage errors rather than imply absence."""
        if self._initialization_error is not None:
            raise ProviderError("OFFLINE_DB_UNAVAILABLE") from self._initialization_error
        if not doi_str:
            return None

        norm_doi = ReferenceResolver.normalize_doi(doi_str)
        if not norm_doi:
            return None

        if norm_doi in self._retracted_set:
            info = self._records_map.get(norm_doi, {})
            return self._with_evidence({
                "matched": True,
                "is_retracted": True,
                "doi": norm_doi,
                "title": info.get("title", f"Retracted Paper ({norm_doi})"),
                "journal": info.get("journal", "Academic Journal"),
                "reason": info.get("reason", "Retraction Notice Issued"),
                "source": "Offline Retraction Watch Index"
            })

        # Query SQLite if not found in memory cache
        if self._conn:
            try:
                cursor = self._conn.cursor()
                cursor.execute("SELECT doi, title, journal, retraction_date, reason FROM retractions WHERE doi = ?", (norm_doi,))
                row = cursor.fetchone()
                if row:
                    self._retracted_set.add(norm_doi)
                    res = {
                        "matched": True,
                        "is_retracted": True,
                        "doi": row[0],
                        "title": row[1],
                        "journal": row[2],
                        "date": row[3],
                        "reason": row[4],
                        "source": "Offline Retraction Watch SQLite"
                    }
                    self._records_map[norm_doi] = res
                    return self._with_evidence(res)
            except sqlite3.Error as exc:
                raise ProviderError("OFFLINE_DB_UNAVAILABLE") from exc

        return None

    @staticmethod
    def _with_evidence(record):
        """Keep the database record and its evidence strength together."""
        result = dict(record)
        result["retraction_status"] = "CONFIRMED"
        result["retraction_info"] = record.get("reason")
        result["sources"] = [{
            "source": record["source"], "kind": "offline_database",
            "identifier": record["doi"], "detail": record.get("reason"),
            "is_retracted": True,
        }]
        return result

    def close(self):
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            finally:
                self._conn = None
