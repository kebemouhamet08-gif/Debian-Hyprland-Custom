"""Persistent wallpaper playback history."""

from __future__ import annotations

from datetime import datetime, timezone

from .config import validate_output_name
from .library import Library
from .models import HistoryEntry


HISTORY_REASONS = {"manual", "playlist", "random", "restore", "automation"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _datetime(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


class HistoryManager:
    def __init__(self, library: Library):
        self.library = library

    def start(
        self,
        wallpaper_id: int | None,
        output: str,
        reason: str = "manual",
    ) -> HistoryEntry:
        if not validate_output_name(output):
            raise ValueError("invalid output name")
        if reason not in HISTORY_REASONS:
            raise ValueError("invalid history reason")
        self.library.initialize()
        started = _now()
        with self.library._connection() as connection:
            connection.execute(
                "UPDATE history SET ended_at = ? WHERE output = ? AND ended_at IS NULL",
                (started, output),
            )
            cursor = connection.execute(
                "INSERT INTO history(wallpaper_id, output, started_at, reason) VALUES (?, ?, ?, ?)",
                (wallpaper_id, output, started, reason),
            )
            entry_id = cursor.lastrowid
            if wallpaper_id is not None:
                connection.execute("""
                    UPDATE wallpapers
                    SET last_used = ?, usage_count = usage_count + 1
                    WHERE id = ?
                """, (started, wallpaper_id))
        return HistoryEntry(entry_id, wallpaper_id, output, _datetime(started), reason=reason)

    def end(self, entry_id: int) -> HistoryEntry:
        self.library.initialize()
        ended = _now()
        with self.library._connection() as connection:
            if not connection.execute(
                "UPDATE history SET ended_at = ? WHERE id = ? AND ended_at IS NULL",
                (ended, entry_id),
            ).rowcount:
                row = connection.execute(
                    "SELECT * FROM history WHERE id = ?", (entry_id,)
                ).fetchone()
                if row is None:
                    raise KeyError(entry_id)
            row = connection.execute(
                "SELECT * FROM history WHERE id = ?", (entry_id,)
            ).fetchone()
        return self._entry(row)

    def list(self, *, output: str | None = None, limit: int = 100) -> list[HistoryEntry]:
        self.library.initialize()
        if output is not None and not validate_output_name(output):
            raise ValueError("invalid output name")
        query = "SELECT * FROM history"
        parameters = []
        if output is not None:
            query += " WHERE output = ?"
            parameters.append(output)
        query += " ORDER BY started_at DESC LIMIT ?"
        parameters.append(max(1, min(int(limit), 1000)))
        with self.library._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._entry(row) for row in rows]

    @staticmethod
    def _entry(row) -> HistoryEntry:
        return HistoryEntry(
            id=row["id"], wallpaper_id=row["wallpaper_id"], output=row["output"],
            started_at=_datetime(row["started_at"]), ended_at=_datetime(row["ended_at"]),
            reason=row["reason"],
        )
