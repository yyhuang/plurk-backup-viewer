"""Server-side search API backed by SQLite with optional ICU tokenizer."""

import json
import math
import sqlite3
from pathlib import Path

from database import load_icu_extension

RESULTS_PER_PAGE = 50


class SearchDB:
    """Manages SQLite connection and search queries for the API."""

    def __init__(self, db_path: str | Path, icu_extension_path: str | None = None):
        self.db_path = str(db_path)
        self.icu_extension_path = icu_extension_path
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            if self.icu_extension_path:
                load_icu_extension(self._conn, self.icu_extension_path)
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def get_stats(self) -> dict:
        """Return counts for plurks, responses, and links."""
        conn = self._get_conn()
        plurk_count = conn.execute("SELECT COUNT(*) FROM plurks").fetchone()[0]
        response_count = conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0]

        link_count = 0
        link_with_og = 0
        link_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='link_metadata'"
        ).fetchone()
        if link_table:
            link_count = conn.execute("SELECT COUNT(*) FROM link_metadata").fetchone()[0]
            link_with_og = conn.execute(
                "SELECT COUNT(*) FROM link_metadata WHERE status = 'success'"
            ).fetchone()[0]

        return {
            "plurk_count": plurk_count,
            "response_count": response_count,
            "link_count": link_count,
            "link_with_og": link_with_og,
        }

    def search(self, query: str, search_type: str, mode: str, page: int) -> dict:
        """Execute search and return paginated results.

        Args:
            query: Search query string
            search_type: 'all', 'plurks', 'responses', or 'links'
            mode: 'fts' or 'like'
            page: 0-indexed page number

        Returns:
            Dict with results, total, page, pages keys
        """
        if search_type == "links":
            return self._search_links(query, mode, page)
        return self._search_content(query, search_type, mode, page)

    def _search_content(self, query: str, search_type: str, mode: str, page: int) -> dict:
        conn = self._get_conn()
        offset = page * RESULTS_PER_PAGE
        results = []
        total_count = 0

        if mode == "fts":
            fts_query = self._build_fts_query(query)

            if search_type in ("all", "plurks"):
                rows = conn.execute(
                    """
                    SELECT p.id, p.base_id, p.content_raw, p.posted, p.qualifier,
                           p.response_count, 'plurk' as type
                    FROM plurks p
                    JOIN plurks_fts ON plurks_fts.rowid = p.id
                    WHERE plurks_fts MATCH ?
                    ORDER BY p.posted DESC
                    LIMIT ? OFFSET ?
                    """,
                    (fts_query, RESULTS_PER_PAGE, offset),
                ).fetchall()
                results.extend(self._rows_to_content_dicts(rows))

                count = conn.execute(
                    "SELECT COUNT(*) FROM plurks_fts WHERE plurks_fts MATCH ?",
                    (fts_query,),
                ).fetchone()[0]
                total_count += count

            if search_type in ("all", "responses"):
                rows = conn.execute(
                    """
                    SELECT r.id, r.base_id, r.content_raw, r.posted, r.user_nick,
                           r.user_display, 'response' as type
                    FROM responses r
                    JOIN responses_fts ON responses_fts.rowid = r.id
                    WHERE responses_fts MATCH ?
                    ORDER BY r.posted DESC
                    LIMIT ? OFFSET ?
                    """,
                    (fts_query, RESULTS_PER_PAGE, offset),
                ).fetchall()
                results.extend(self._rows_to_content_dicts(rows))

                count = conn.execute(
                    "SELECT COUNT(*) FROM responses_fts WHERE responses_fts MATCH ?",
                    (fts_query,),
                ).fetchone()[0]
                total_count += count

        else:
            like_pattern = self._build_like_pattern(query)

            if search_type in ("all", "plurks"):
                rows = conn.execute(
                    """
                    SELECT id, base_id, content_raw, posted, qualifier,
                           response_count, 'plurk' as type
                    FROM plurks
                    WHERE content_raw LIKE ? ESCAPE '\\'
                    ORDER BY posted DESC
                    LIMIT ? OFFSET ?
                    """,
                    (like_pattern, RESULTS_PER_PAGE, offset),
                ).fetchall()
                results.extend(self._rows_to_content_dicts(rows))

                count = conn.execute(
                    "SELECT COUNT(*) FROM plurks WHERE content_raw LIKE ? ESCAPE '\\'",
                    (like_pattern,),
                ).fetchone()[0]
                total_count += count

            if search_type in ("all", "responses"):
                rows = conn.execute(
                    """
                    SELECT id, base_id, content_raw, posted, user_nick,
                           user_display, 'response' as type
                    FROM responses
                    WHERE content_raw LIKE ? ESCAPE '\\'
                    ORDER BY posted DESC
                    LIMIT ? OFFSET ?
                    """,
                    (like_pattern, RESULTS_PER_PAGE, offset),
                ).fetchall()
                results.extend(self._rows_to_content_dicts(rows))

                count = conn.execute(
                    "SELECT COUNT(*) FROM responses WHERE content_raw LIKE ? ESCAPE '\\'",
                    (like_pattern,),
                ).fetchone()[0]
                total_count += count

        # Sort combined results by date descending
        results.sort(key=lambda r: r.get("posted") or "", reverse=True)

        total_pages = max(1, math.ceil(total_count / RESULTS_PER_PAGE))
        return {
            "results": results,
            "total": total_count,
            "page": page,
            "pages": total_pages,
        }

    def _search_links(self, query: str, mode: str, page: int) -> dict:
        conn = self._get_conn()
        offset = page * RESULTS_PER_PAGE

        # Check if link_metadata table exists
        table_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='link_metadata'"
        ).fetchone()
        if not table_exists:
            return {"results": [], "total": 0, "page": page, "pages": 1,
                    "error": "Link search not available. Run plurk-tools links extract first."}

        if mode == "fts":
            fts_exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='link_metadata_fts'"
            ).fetchone()
            if not fts_exists:
                return {"results": [], "total": 0, "page": page, "pages": 1,
                        "error": "FTS index not available for links."}

            fts_query = self._build_fts_query(query)
            rows = conn.execute(
                """
                SELECT lm.url, lm.og_title, lm.og_description, lm.og_site_name,
                       lm.sources, lm.status
                FROM link_metadata lm
                JOIN link_metadata_fts ON link_metadata_fts.rowid = lm.rowid
                WHERE link_metadata_fts MATCH ?
                ORDER BY lm.rowid DESC
                LIMIT ? OFFSET ?
                """,
                (fts_query, RESULTS_PER_PAGE, offset),
            ).fetchall()

            total_count = conn.execute(
                "SELECT COUNT(*) FROM link_metadata_fts WHERE link_metadata_fts MATCH ?",
                (fts_query,),
            ).fetchone()[0]
        else:
            like_pattern = self._build_like_pattern(query)
            rows = conn.execute(
                """
                SELECT url, og_title, og_description, og_site_name, sources, status
                FROM link_metadata
                WHERE url LIKE ? ESCAPE '\\'
                   OR og_title LIKE ? ESCAPE '\\'
                   OR og_description LIKE ? ESCAPE '\\'
                   OR og_site_name LIKE ? ESCAPE '\\'
                ORDER BY rowid DESC
                LIMIT ? OFFSET ?
                """,
                (like_pattern, like_pattern, like_pattern, like_pattern,
                 RESULTS_PER_PAGE, offset),
            ).fetchall()

            total_count = conn.execute(
                """
                SELECT COUNT(*) FROM link_metadata
                WHERE url LIKE ? ESCAPE '\\'
                   OR og_title LIKE ? ESCAPE '\\'
                   OR og_description LIKE ? ESCAPE '\\'
                   OR og_site_name LIKE ? ESCAPE '\\'
                """,
                (like_pattern, like_pattern, like_pattern, like_pattern),
            ).fetchone()[0]

        results = []
        for row in rows:
            sources = json.loads(row[4]) if row[4] else {}
            results.append({
                "url": row[0],
                "og_title": row[1],
                "og_description": row[2],
                "og_site_name": row[3],
                "sources": sources,
                "status": row[5],
                "type": "link",
            })

        total_pages = max(1, math.ceil(total_count / RESULTS_PER_PAGE))
        return {
            "results": results,
            "total": total_count,
            "page": page,
            "pages": total_pages,
        }

    def get_plurk(self, plurk_id: int) -> dict | None:
        """Look up a plurk by ID, returning base_id and posted."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT base_id, posted FROM plurks WHERE id = ?", (plurk_id,)
        ).fetchone()
        if row:
            return {"base_id": row[0], "posted": row[1]}
        return None

    def get_response_plurk(self, response_id: int) -> dict | None:
        """Look up a response's parent plurk by response ID."""
        conn = self._get_conn()
        row = conn.execute(
            """
            SELECT r.base_id, p.posted
            FROM responses r
            JOIN plurks p ON r.base_id = p.base_id
            WHERE r.id = ?
            """,
            (response_id,),
        ).fetchone()
        if row:
            return {"base_id": row[0], "posted": row[1]}
        return None

    @staticmethod
    def _build_fts_query(query: str) -> str:
        """Build FTS5 MATCH query from user input.

        Each term is quoted and gets a * suffix for prefix matching.
        No CJK special-casing needed when using ICU tokenizer.
        """
        terms = query.strip().split()
        parts = []
        for term in terms:
            escaped = term.replace('"', '""')
            parts.append(f'"{escaped}"*')
        return " ".join(parts)

    @staticmethod
    def _build_like_pattern(query: str) -> str:
        """Build LIKE pattern from user input."""
        escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"

    @staticmethod
    def _rows_to_content_dicts(rows: list) -> list[dict]:
        """Convert sqlite3.Row results to dicts for content search."""
        results = []
        for row in rows:
            record_type = row[6]
            if record_type == "plurk":
                results.append({
                    "id": row[0],
                    "base_id": row[1],
                    "content_raw": row[2],
                    "posted": row[3],
                    "qualifier": row[4],
                    "response_count": row[5],
                    "type": "plurk",
                })
            else:
                results.append({
                    "id": row[0],
                    "base_id": row[1],
                    "content_raw": row[2],
                    "posted": row[3],
                    "user_nick": row[4],
                    "user_display": row[5],
                    "type": "response",
                })
        return results
