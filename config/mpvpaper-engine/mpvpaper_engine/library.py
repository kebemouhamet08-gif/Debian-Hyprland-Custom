"""SQLite-backed local wallpaper Library, separate from recommendations."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import subprocess
from typing import Callable, Iterable

from .metadata import (
    MEDIA_EXTENSIONS,
    MediaMetadata,
    content_signature,
    generate_thumbnail,
    probe_media,
    scan_fingerprint,
)
from .models import MediaType, Wallpaper
from .paths import EnginePaths


SCHEMA_VERSION = 1


SCHEMA = """
CREATE TABLE IF NOT EXISTS wallpapers (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('image', 'video')),
    duration REAL,
    width INTEGER,
    height INTEGER,
    fps REAL,
    video_codec TEXT,
    audio_codec TEXT,
    bitrate INTEGER,
    file_size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    fingerprint TEXT NOT NULL,
    content_signature TEXT,
    thumbnail_path TEXT,
    source TEXT NOT NULL DEFAULT 'local',
    source_url TEXT,
    favorite INTEGER NOT NULL DEFAULT 0,
    date_added TEXT NOT NULL,
    last_used TEXT,
    usage_count INTEGER NOT NULL DEFAULT 0,
    missing INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS wallpapers_title_idx ON wallpapers(title);
CREATE INDEX IF NOT EXISTS wallpapers_type_idx ON wallpapers(type);
CREATE INDEX IF NOT EXISTS wallpapers_favorite_idx ON wallpapers(favorite);
CREATE INDEX IF NOT EXISTS wallpapers_signature_idx ON wallpapers(content_signature);
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS wallpaper_tags (
    wallpaper_id INTEGER NOT NULL REFERENCES wallpapers(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (wallpaper_id, tag_id)
);
CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    mode TEXT NOT NULL DEFAULT 'sequential',
    interval_seconds INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS playlist_items (
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    wallpaper_id INTEGER NOT NULL REFERENCES wallpapers(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY (playlist_id, wallpaper_id)
);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY,
    wallpaper_id INTEGER REFERENCES wallpapers(id) ON DELETE SET NULL,
    output TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    reason TEXT NOT NULL DEFAULT 'manual'
);
CREATE TABLE IF NOT EXISTS cache_entries (
    path TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    size INTEGER NOT NULL,
    last_accessed REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""


def _utc_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _datetime(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


class LibraryError(RuntimeError):
    pass


class Library:
    def __init__(
        self,
        paths: EnginePaths | None = None,
        *,
        probe: Callable[[Path], MediaMetadata] = probe_media,
        thumbnail_builder: Callable = generate_thumbnail,
        trash_runner: Callable = subprocess.run,
    ):
        self.paths = paths or EnginePaths.from_environment()
        self.probe = probe
        self.thumbnail_builder = thumbnail_builder
        self.trash_runner = trash_runner

    def initialize(self) -> None:
        self.paths.data_home.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(SCHEMA)
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, _utc_text()),
            )
        self.paths.library_db.chmod(0o600)

    def _connect(self):
        connection = sqlite3.connect(self.paths.library_db, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def import_file(
        self,
        path: Path,
        *,
        source: str = "local",
        source_url: str | None = None,
    ) -> Wallpaper:
        self.initialize()
        path = Path(path).expanduser().resolve()
        if not path.is_file() or path.suffix.casefold() not in MEDIA_EXTENSIONS:
            raise ValueError("media is missing or unsupported")
        info = path.stat()
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT * FROM wallpapers WHERE path = ?", (str(path),)
            ).fetchone()
            if (
                existing is not None
                and existing["file_size"] == info.st_size
                and existing["mtime_ns"] == info.st_mtime_ns
            ):
                if existing["missing"]:
                    connection.execute(
                        "UPDATE wallpapers SET missing = 0 WHERE id = ?", (existing["id"],)
                    )
                    existing = connection.execute(
                        "SELECT * FROM wallpapers WHERE id = ?", (existing["id"],)
                    ).fetchone()
                return self._wallpaper(existing)

        metadata = self.probe(path)
        fingerprint = scan_fingerprint(path)
        signature = content_signature(path)
        now = _utc_text()
        with self._connection() as connection:
            connection.execute("""
                INSERT INTO wallpapers (
                    path, title, type, duration, width, height, fps,
                    video_codec, audio_codec, bitrate, file_size, mtime_ns,
                    fingerprint, content_signature, source, source_url, date_added
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    title=excluded.title, type=excluded.type,
                    duration=excluded.duration, width=excluded.width,
                    height=excluded.height, fps=excluded.fps,
                    video_codec=excluded.video_codec, audio_codec=excluded.audio_codec,
                    bitrate=excluded.bitrate, file_size=excluded.file_size,
                    mtime_ns=excluded.mtime_ns, fingerprint=excluded.fingerprint,
                    content_signature=excluded.content_signature,
                    source=excluded.source, source_url=excluded.source_url, missing=0
            """, (
                str(path), path.stem, metadata.media_type.value,
                metadata.duration, metadata.width, metadata.height, metadata.fps,
                metadata.video_codec, metadata.audio_codec, metadata.bitrate,
                info.st_size, info.st_mtime_ns, fingerprint, signature,
                source, source_url, now,
            ))
            row = connection.execute(
                "SELECT * FROM wallpapers WHERE path = ?", (str(path),)
            ).fetchone()
        return self._wallpaper(row)

    def scan(self, roots: Iterable[Path]) -> dict[str, int]:
        self.initialize()
        canonical_roots = [Path(root).expanduser().resolve() for root in roots]
        found = set()
        imported = 0
        unchanged = 0
        for root in canonical_roots:
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if path.is_file() and path.suffix.casefold() in MEDIA_EXTENSIONS:
                    resolved = path.resolve()
                    found.add(str(resolved))
                    before = self.get_by_path(resolved)
                    self.import_file(resolved)
                    if before and before.file_size == resolved.stat().st_size and before.mtime_ns == resolved.stat().st_mtime_ns:
                        unchanged += 1
                    else:
                        imported += 1
        missing = 0
        with self._connection() as connection:
            rows = connection.execute("SELECT id, path, missing FROM wallpapers").fetchall()
            for row in rows:
                path = Path(row["path"])
                managed = any(path == root or root in path.parents for root in canonical_roots)
                should_be_missing = managed and str(path) not in found
                if should_be_missing and not row["missing"]:
                    connection.execute(
                        "UPDATE wallpapers SET missing = 1 WHERE id = ?", (row["id"],)
                    )
                    missing += 1
        return {"imported": imported, "unchanged": unchanged, "missing": missing}

    def get(self, wallpaper_id: int) -> Wallpaper | None:
        self.initialize()
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM wallpapers WHERE id = ?", (wallpaper_id,)
            ).fetchone()
        return self._wallpaper(row) if row else None

    def get_by_path(self, path: Path) -> Wallpaper | None:
        self.initialize()
        resolved = str(Path(path).expanduser().resolve())
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM wallpapers WHERE path = ?", (resolved,)
            ).fetchone()
        return self._wallpaper(row) if row else None

    def list(
        self,
        *,
        media_type: MediaType | str | None = None,
        favorites_only: bool = False,
        include_missing: bool = False,
        limit: int = 1000,
    ) -> list[Wallpaper]:
        return self.search(
            "", media_type=media_type, favorites_only=favorites_only,
            include_missing=include_missing, limit=limit,
        )

    def search(
        self,
        query: str,
        *,
        media_type: MediaType | str | None = None,
        favorites_only: bool = False,
        include_missing: bool = False,
        limit: int = 1000,
    ) -> list[Wallpaper]:
        self.initialize()
        clauses = ["(title LIKE ? ESCAPE '\\' OR path LIKE ? ESCAPE '\\')"]
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        parameters: list = [f"%{escaped}%", f"%{escaped}%"]
        if media_type is not None:
            value = media_type.value if isinstance(media_type, MediaType) else str(media_type)
            if value not in {"image", "video"}:
                raise ValueError("invalid media type")
            clauses.append("type = ?")
            parameters.append(value)
        if favorites_only:
            clauses.append("favorite = 1")
        if not include_missing:
            clauses.append("missing = 0")
        parameters.append(max(1, min(int(limit), 10000)))
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM wallpapers WHERE {' AND '.join(clauses)} "
                "ORDER BY favorite DESC, title COLLATE NOCASE LIMIT ?",
                parameters,
            ).fetchall()
        return [self._wallpaper(row) for row in rows]

    def set_favorite(self, wallpaper_id: int, favorite: bool) -> Wallpaper:
        if not isinstance(favorite, bool):
            raise ValueError("favorite must be boolean")
        self.initialize()
        with self._connection() as connection:
            changed = connection.execute(
                "UPDATE wallpapers SET favorite = ? WHERE id = ?",
                (int(favorite), wallpaper_id),
            ).rowcount
        if not changed:
            raise KeyError(wallpaper_id)
        return self.get(wallpaper_id)

    def mark_missing(self, wallpaper_id: int, missing: bool = True) -> None:
        if not isinstance(missing, bool):
            raise ValueError("missing must be boolean")
        self.initialize()
        with self._connection() as connection:
            if not connection.execute(
                "UPDATE wallpapers SET missing = ? WHERE id = ?",
                (int(missing), wallpaper_id),
            ).rowcount:
                raise KeyError(wallpaper_id)

    def find_duplicate(self, path: Path) -> Wallpaper | None:
        signature = content_signature(path)
        self.initialize()
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM wallpapers WHERE content_signature = ? AND path != ? LIMIT 1",
                (signature, str(Path(path).expanduser().resolve())),
            ).fetchone()
        return self._wallpaper(row) if row else None

    def rebuild_thumbnail(self, wallpaper_id: int) -> Path:
        wallpaper = self.get(wallpaper_id)
        if wallpaper is None:
            raise KeyError(wallpaper_id)
        if not wallpaper.path.is_file():
            self.mark_missing(wallpaper_id)
            raise LibraryError("wallpaper file is missing")
        destination = self.thumbnail_builder(wallpaper.path, self.paths.thumbnail_dir)
        with self._connection() as connection:
            connection.execute(
                "UPDATE wallpapers SET thumbnail_path = ? WHERE id = ?",
                (str(destination), wallpaper_id),
            )
        return destination

    def delete_to_trash(
        self,
        wallpaper_id: int,
        *,
        library_roots: Iterable[Path],
        protected_paths: Iterable[Path] = (),
    ) -> None:
        wallpaper = self.get(wallpaper_id)
        if wallpaper is None:
            raise KeyError(wallpaper_id)
        candidate = wallpaper.path.resolve(strict=True)
        roots = [Path(root).expanduser().resolve() for root in library_roots]
        if not any(candidate == root or root in candidate.parents for root in roots):
            raise LibraryError("wallpaper is outside managed Library roots")
        protected = {Path(path).expanduser().resolve() for path in protected_paths}
        if candidate in protected:
            raise LibraryError("wallpaper is currently assigned")
        result = self.trash_runner(
            ["gio", "trash", str(candidate)], capture_output=True,
            text=True, timeout=10, check=False,
        )
        if result.returncode != 0:
            raise LibraryError(result.stderr.strip() or "unable to move wallpaper to trash")
        self.mark_missing(wallpaper_id)

    @staticmethod
    def _wallpaper(row: sqlite3.Row) -> Wallpaper:
        return Wallpaper(
            id=row["id"], path=Path(row["path"]), title=row["title"],
            media_type=MediaType(row["type"]), duration=row["duration"],
            width=row["width"], height=row["height"], fps=row["fps"],
            video_codec=row["video_codec"], audio_codec=row["audio_codec"],
            bitrate=row["bitrate"], file_size=row["file_size"],
            mtime_ns=row["mtime_ns"], fingerprint=row["fingerprint"],
            content_signature=row["content_signature"],
            thumbnail_path=Path(row["thumbnail_path"]) if row["thumbnail_path"] else None,
            source=row["source"], source_url=row["source_url"],
            favorite=bool(row["favorite"]), date_added=_datetime(row["date_added"]),
            last_used=_datetime(row["last_used"]), usage_count=row["usage_count"],
            missing=bool(row["missing"]),
        )
