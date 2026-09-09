"""Persistent playlists, deterministic ordering and local Smart Shuffle."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import random
from typing import Any

from .library import Library
from .models import Playlist, PlaylistMode, Wallpaper


INTERVALS = {300, 600, 1800, 3600, 7200}
SCHEDULE_EVENTS = {"login", "unlock"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _datetime(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class PlaylistManager:
    def __init__(self, library: Library, rng: random.Random | None = None):
        self.library = library
        self.rng = rng or random.Random()

    def create(
        self,
        name: str,
        mode: PlaylistMode | str = PlaylistMode.SEQUENTIAL,
        interval_seconds: int | None = None,
    ) -> Playlist:
        name = name.strip() if isinstance(name, str) else ""
        if not name:
            raise ValueError("playlist name is required")
        selected = self._mode(mode)
        interval = self._interval(interval_seconds)
        self.library.initialize()
        now = _now()
        with self.library._connection() as connection:
            cursor = connection.execute(
                "INSERT INTO playlists(name, mode, interval_seconds, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, selected.value, interval, now, now),
            )
            playlist_id = cursor.lastrowid
        return Playlist(playlist_id, name, selected, interval, _datetime(now), _datetime(now))

    def delete(self, playlist_id: int) -> None:
        self.library.initialize()
        with self.library._connection() as connection:
            if not connection.execute(
                "DELETE FROM playlists WHERE id = ?", (playlist_id,)
            ).rowcount:
                raise KeyError(playlist_id)

    def rename(self, playlist_id: int, name: str) -> Playlist:
        name = name.strip() if isinstance(name, str) else ""
        if not name:
            raise ValueError("playlist name is required")
        self._update(playlist_id, "name", name)
        return self.get(playlist_id)

    def configure(
        self,
        playlist_id: int,
        *,
        mode: PlaylistMode | str,
        interval_seconds: int | None,
    ) -> Playlist:
        selected = self._mode(mode)
        interval = self._interval(interval_seconds)
        self.library.initialize()
        with self.library._connection() as connection:
            if not connection.execute(
                "UPDATE playlists SET mode = ?, interval_seconds = ?, updated_at = ? WHERE id = ?",
                (selected.value, interval, _now(), playlist_id),
            ).rowcount:
                raise KeyError(playlist_id)
        return self.get(playlist_id)

    def get(self, playlist_id: int) -> Playlist:
        self.library.initialize()
        with self.library._connection() as connection:
            row = connection.execute(
                "SELECT * FROM playlists WHERE id = ?", (playlist_id,)
            ).fetchone()
        if row is None:
            raise KeyError(playlist_id)
        return self._playlist(row)

    def list(self) -> list[Playlist]:
        self.library.initialize()
        with self.library._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM playlists ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [self._playlist(row) for row in rows]

    def add(self, playlist_id: int, wallpaper_id: int, *, weight: float = 1.0) -> None:
        if weight <= 0:
            raise ValueError("weight must be positive")
        self.get(playlist_id)
        if self.library.get(wallpaper_id) is None:
            raise KeyError(wallpaper_id)
        with self.library._connection() as connection:
            position = connection.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM playlist_items WHERE playlist_id = ?",
                (playlist_id,),
            ).fetchone()[0]
            connection.execute("""
                INSERT INTO playlist_items(playlist_id, wallpaper_id, position, weight)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(playlist_id, wallpaper_id)
                DO UPDATE SET weight=excluded.weight
            """, (playlist_id, wallpaper_id, position, float(weight)))
            self._touch(connection, playlist_id)

    def remove(self, playlist_id: int, wallpaper_id: int) -> None:
        self.get(playlist_id)
        with self.library._connection() as connection:
            if not connection.execute(
                "DELETE FROM playlist_items WHERE playlist_id = ? AND wallpaper_id = ?",
                (playlist_id, wallpaper_id),
            ).rowcount:
                raise KeyError(wallpaper_id)
            self._compact(connection, playlist_id)
            self._touch(connection, playlist_id)

    def reorder(self, playlist_id: int, wallpaper_ids: list[int]) -> None:
        current = [item.id for item in self.items(playlist_id, include_missing=True)]
        if len(wallpaper_ids) != len(set(wallpaper_ids)) or set(wallpaper_ids) != set(current):
            raise ValueError("reorder must contain every playlist item exactly once")
        with self.library._connection() as connection:
            for position, wallpaper_id in enumerate(wallpaper_ids):
                connection.execute(
                    "UPDATE playlist_items SET position = ? WHERE playlist_id = ? AND wallpaper_id = ?",
                    (position, playlist_id, wallpaper_id),
                )
            self._touch(connection, playlist_id)

    def items(self, playlist_id: int, *, include_missing: bool = False) -> list[Wallpaper]:
        self.get(playlist_id)
        missing_clause = "" if include_missing else "AND w.missing = 0"
        with self.library._connection() as connection:
            rows = connection.execute(f"""
                SELECT w.* FROM playlist_items pi
                JOIN wallpapers w ON w.id = pi.wallpaper_id
                WHERE pi.playlist_id = ? {missing_clause}
                ORDER BY pi.position
            """, (playlist_id,)).fetchall()
        return [self.library._wallpaper(row) for row in rows]

    def next(
        self,
        playlist_id: int,
        *,
        current_id: int | None = None,
        output: str | None = None,
        recent_count: int = 5,
    ) -> Wallpaper | None:
        playlist = self.get(playlist_id)
        items = self.items(playlist_id)
        if not items:
            return None
        if playlist.mode == PlaylistMode.SEQUENTIAL:
            ids = [item.id for item in items]
            index = ids.index(current_id) + 1 if current_id in ids else 0
            return items[index % len(items)]
        if playlist.mode == PlaylistMode.SHUFFLE:
            alternatives = [item for item in items if item.id != current_id]
            return self.rng.choice(alternatives or items)
        return self._smart(
            playlist_id, items, output=output, recent_count=recent_count
        )

    def _smart(self, playlist_id, items, *, output, recent_count):
        recent = set()
        if recent_count > 0:
            query = "SELECT wallpaper_id FROM history WHERE wallpaper_id IS NOT NULL"
            parameters: list[Any] = []
            if output is not None:
                query += " AND output = ?"
                parameters.append(output)
            query += " ORDER BY started_at DESC LIMIT ?"
            parameters.append(recent_count)
            with self.library._connection() as connection:
                recent = {row[0] for row in connection.execute(query, parameters)}
        eligible = [item for item in items if item.id not in recent] or items
        weights = []
        with self.library._connection() as connection:
            item_weights = {
                row[0]: row[1] for row in connection.execute(
                    "SELECT wallpaper_id, weight FROM playlist_items WHERE playlist_id = ?",
                    (playlist_id,),
                )
            }
        for item in eligible:
            base = item_weights.get(item.id, 1.0)
            favorite_bonus = 2.0 if item.favorite else 1.0
            rare_bonus = 1.0 + 1.0 / (1 + item.usage_count)
            weights.append(base * favorite_bonus * rare_bonus)
        return self.rng.choices(eligible, weights=weights, k=1)[0]

    def next_deadline(self, playlist_id: int, now: datetime | None = None) -> datetime | None:
        interval = self.get(playlist_id).interval_seconds
        return (now or datetime.now(timezone.utc)) + timedelta(seconds=interval) if interval else None

    @staticmethod
    def should_advance(event: str) -> bool:
        return event in SCHEDULE_EVENTS

    def _update(self, playlist_id, field, value):
        self.library.initialize()
        if field != "name":
            raise ValueError("unsupported playlist field")
        with self.library._connection() as connection:
            if not connection.execute(
                f"UPDATE playlists SET {field} = ?, updated_at = ? WHERE id = ?",
                (value, _now(), playlist_id),
            ).rowcount:
                raise KeyError(playlist_id)

    @staticmethod
    def _mode(mode):
        try:
            return mode if isinstance(mode, PlaylistMode) else PlaylistMode(mode)
        except ValueError as error:
            raise ValueError("invalid playlist mode") from error

    @staticmethod
    def _interval(value):
        if value is not None and value not in INTERVALS:
            raise ValueError("invalid playlist interval")
        return value

    @staticmethod
    def _touch(connection, playlist_id):
        connection.execute(
            "UPDATE playlists SET updated_at = ? WHERE id = ?", (_now(), playlist_id)
        )

    @staticmethod
    def _compact(connection, playlist_id):
        rows = connection.execute(
            "SELECT wallpaper_id FROM playlist_items WHERE playlist_id = ? ORDER BY position",
            (playlist_id,),
        ).fetchall()
        for position, row in enumerate(rows):
            connection.execute(
                "UPDATE playlist_items SET position = ? WHERE playlist_id = ? AND wallpaper_id = ?",
                (position, playlist_id, row[0]),
            )

    @staticmethod
    def _playlist(row):
        return Playlist(
            row["id"], row["name"], PlaylistMode(row["mode"]), row["interval_seconds"],
            _datetime(row["created_at"]), _datetime(row["updated_at"]),
        )
