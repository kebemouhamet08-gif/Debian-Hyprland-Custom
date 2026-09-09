"""Private local recommendation ranking over the preserved suggestions database."""

from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import time
from urllib.parse import urlparse
from .paths import EnginePaths


MIN_SUGGESTIONS = 4
MAX_SUGGESTIONS = 60
DEFAULT_SUGGESTIONS = 16


@dataclass(frozen=True, slots=True)
class Recommendation:
    uri: str
    title: str
    source: str
    tags: tuple[str, ...]
    rating: float
    confidence: float
    external_views: int
    external_likes: int
    thumbnail: Path


class RecommendationEngine:
    def __init__(self, paths: EnginePaths | None = None):
        self.paths = paths or EnginePaths.from_environment()
        self.database = self.paths.recommendations_db
        self.settings_file = self.paths.data_home / "recommendation-settings.json"

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.database, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def sources(self) -> dict[str, int]:
        if not self.database.is_file():
            return {}
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT source, COUNT(*) AS count FROM candidates GROUP BY source "
                "ORDER BY count DESC, source"
            ).fetchall()
        return {row["source"]: row["count"] for row in rows}

    def settings(self) -> dict:
        available = self.sources()
        try:
            data = json.loads(self.settings_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        enabled = data.get("enabled_sources")
        if not isinstance(enabled, list):
            enabled = list(available)
        enabled = [source for source in enabled if source in available]
        limit = data.get("limit", DEFAULT_SUGGESTIONS)
        if not isinstance(limit, int):
            limit = DEFAULT_SUGGESTIONS
        return {
            "enabled_sources": enabled,
            "limit": max(MIN_SUGGESTIONS, min(MAX_SUGGESTIONS, limit)),
        }

    def configure(self, *, enabled_sources=None, limit=None) -> dict:
        values = self.settings()
        available = self.sources()
        if enabled_sources is not None:
            values["enabled_sources"] = [
                source for source in enabled_sources if source in available
            ]
        if limit is not None:
            values["limit"] = max(MIN_SUGGESTIONS, min(MAX_SUGGESTIONS, int(limit)))
        self._atomic_write(values)
        return values

    def recommend(self, *, limit=None, enabled_sources=None) -> list[Recommendation]:
        if not self.database.is_file():
            return []
        settings = self.settings()
        selected_sources = list(
            settings["enabled_sources"] if enabled_sources is None else enabled_sources
        )
        wanted = settings["limit"] if limit is None else max(
            MIN_SUGGESTIONS, min(MAX_SUGGESTIONS, int(limit))
        )
        if not selected_sources:
            return []
        placeholders = ",".join("?" for _ in selected_sources)
        with self._connection() as connection:
            profile = dict(connection.execute("SELECT tag, weight FROM tag_profile"))
            rows = connection.execute(
                f"SELECT * FROM candidates WHERE source IN ({placeholders})",
                selected_sources,
            ).fetchall()
        grouped = defaultdict(list)
        for row in rows:
            tags = tuple(filter(None, row["tags"].split()))
            affinity = sum(float(profile.get(tag, 0)) for tag in tags)
            public = self._public_score(row["external_views"], row["external_likes"])
            learned = float(row["score"]) + affinity * 0.35 - int(row["views"]) * 0.015
            ranking = learned + public
            rating = max(1.0, min(5.0, 3.0 + ranking))
            external_views = int(row["external_views"] or 0)
            external_likes = int(row["external_likes"] or 0)
            confidence = min(1.0, math.log10(external_views + 1) / 6)
            item = Recommendation(
                row["uri"], row["title"], row["source"], tags,
                rating, confidence, external_views,
                external_likes, self.thumbnail_path(row["uri"]),
            )
            grouped[row["source"]].append((ranking, item))
        for items in grouped.values():
            items.sort(key=lambda pair: (-pair[0], pair[1].title.casefold()))
        result = []
        ordered_sources = sorted(grouped, key=lambda source: (-len(grouped[source]), source))
        while len(result) < wanted and any(grouped.values()):
            for source in ordered_sources:
                if grouped[source] and len(result) < wanted:
                    result.append(grouped[source].pop(0)[1])
        return result

    def feedback(self, uri: str, value: int) -> None:
        if value not in {-1, 1}:
            raise ValueError("feedback must be -1 or 1")
        with self._connection() as connection:
            row = connection.execute(
                "SELECT tags FROM candidates WHERE uri = ?", (uri,)
            ).fetchone()
            if row is None:
                raise KeyError(uri)
            connection.execute(
                "UPDATE candidates SET score = score + ?, views = views + 1 WHERE uri = ?",
                (0.8 * value, uri),
            )
            for tag in filter(None, row["tags"].split()):
                connection.execute(
                    "INSERT INTO tag_profile(tag,weight) VALUES(?,?) "
                    "ON CONFLICT(tag) DO UPDATE SET weight=weight+excluded.weight",
                    (tag, 0.25 * value),
                )

    def like(self, uri: str, title: str) -> None:
        """Save an arbitrary browser page as a positive recommendation signal."""
        parsed = urlparse(uri)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("adresse Web invalide")
        source = parsed.hostname.casefold().removeprefix("www.")
        tags = " ".join(dict.fromkeys(
            word for word in re.findall(r"[a-z0-9]+", title.casefold())
            if len(word) > 2 and word not in {"live", "wallpaper", "video", "fond"}
        ))
        self.database.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS candidates(
                  uri TEXT PRIMARY KEY,title TEXT NOT NULL,source TEXT NOT NULL,
                  tags TEXT NOT NULL DEFAULT '',score REAL NOT NULL DEFAULT 0,
                  views INTEGER NOT NULL DEFAULT 0,last_seen INTEGER NOT NULL DEFAULT 0,
                  external_views INTEGER NOT NULL DEFAULT 0,
                  external_likes INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS tag_profile(
                  tag TEXT PRIMARY KEY,weight REAL NOT NULL DEFAULT 0
                );
            """)
            connection.execute(
                "INSERT INTO candidates(uri,title,source,tags,score,views,last_seen,"
                "external_views,external_likes) VALUES(?,?,?,?,0,0,?,0,0) "
                "ON CONFLICT(uri) DO UPDATE SET "
                "title=excluded.title,source=excluded.source,tags=excluded.tags,"
                "last_seen=excluded.last_seen",
                (uri, title or source, source, tags, int(time.time())),
            )
        self.feedback(uri, 1)

    def thumbnail_path(self, uri: str) -> Path:
        return self.paths.suggestion_cache_dir / (
            hashlib.sha256(uri.encode()).hexdigest() + ".preview"
        )

    @staticmethod
    def _public_score(views, likes):
        views = max(0, int(views or 0))
        likes = max(0, int(likes or 0))
        reach = min(1.0, math.log10(views + 1) / 6) if views else 0
        engagement = min(1.0, (likes / views) / 0.08) if views else 0
        return reach * 0.6 + engagement * 0.4

    def _atomic_write(self, data):
        self.paths.data_home.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.paths.data_home,
                prefix=".recommendation-settings-", delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(0o600)
            os.replace(temporary, self.settings_file)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
