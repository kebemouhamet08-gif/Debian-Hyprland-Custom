"""Quota-aware cache index and explicit safe cleanup operations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any

from .paths import EnginePaths


MIB = 1024 * 1024
DEFAULT_TOTAL_QUOTA = 512 * MIB
DEFAULT_CATEGORY_QUOTAS = {
    "suggestions": 256 * MIB,
    "thumbnails": 128 * MIB,
    "temporary": 96 * MIB,
    "palette_log": 32 * MIB,
}
SUGGESTION_MAX_AGE = 30 * 24 * 60 * 60
INDEX_FILENAME = "cache-index.json"


@dataclass(slots=True)
class CacheEntry:
    path: str
    category: str
    size: int
    last_accessed: float


class CacheSafetyError(RuntimeError):
    pass


class CacheManager:
    def __init__(
        self,
        paths: EnginePaths | None = None,
        *,
        total_quota: int = DEFAULT_TOTAL_QUOTA,
        category_quotas: dict[str, int] | None = None,
        suggestion_max_age: int = SUGGESTION_MAX_AGE,
        library_roots: tuple[Path, ...] = (),
    ):
        self.paths = paths or EnginePaths.from_environment()
        self.total_quota = max(0, int(total_quota))
        self.category_quotas = {
            **DEFAULT_CATEGORY_QUOTAS, **(category_quotas or {})
        }
        self.suggestion_max_age = max(0, int(suggestion_max_age))
        self.library_roots = tuple(Path(root).expanduser().resolve() for root in library_roots)
        self.index_file = self.paths.cache_home / INDEX_FILENAME

    def _roots(self) -> dict[str, tuple[Path, ...]]:
        return {
            "suggestions": (self.paths.suggestion_cache_dir,),
            "thumbnails": (self.paths.thumbnail_dir,),
            "temporary": (self.paths.temp_dir,),
            "palette_log": (self.paths.palette_dir, self.paths.log_dir),
        }

    def _scan(self) -> list[CacheEntry]:
        entries = []
        for category, roots in self._roots().items():
            for root in roots:
                if not root.is_dir():
                    continue
                for path in root.rglob("*"):
                    if not path.is_file():
                        continue
                    try:
                        info = path.stat()
                        relative = path.relative_to(self.paths.cache_home)
                    except (OSError, ValueError):
                        continue
                    entries.append(CacheEntry(
                        path=str(relative), category=category, size=info.st_size,
                        last_accessed=max(info.st_atime, info.st_mtime),
                    ))
        return entries

    def stats(self) -> dict[str, Any]:
        entries = self._scan()
        categories = {
            category: {"size": 0, "entries": 0, "quota": quota}
            for category, quota in self.category_quotas.items()
        }
        for entry in entries:
            value = categories.setdefault(entry.category, {"size": 0, "entries": 0, "quota": 0})
            value["size"] += entry.size
            value["entries"] += 1
        return {
            "total_size": sum(entry.size for entry in entries),
            "total_entries": len(entries),
            "total_quota": self.total_quota,
            "categories": categories,
        }

    def rebuild_index(self) -> dict[str, Any]:
        entries = self._scan()
        data = {
            "version": 1,
            "generated_at": time.time(),
            "entries": [asdict(entry) for entry in entries],
        }
        self._atomic_write(data)
        return {"entries": len(entries), "size": sum(entry.size for entry in entries)}

    def touch(self, path: Path) -> None:
        candidate = self._safe_candidate(path)
        now = time.time()
        os.utime(candidate, (now, candidate.stat().st_mtime))

    def clean_expired(self, *, now: float | None = None) -> dict[str, int]:
        current = time.time() if now is None else now
        entries = [
            entry for entry in self._scan()
            if entry.category == "suggestions"
            and current - entry.last_accessed > self.suggestion_max_age
        ]
        return self._delete_entries(entries)

    def enforce_quotas(self) -> dict[str, int]:
        entries = self._scan()
        selected: dict[str, CacheEntry] = {}
        for category, quota in self.category_quotas.items():
            category_entries = sorted(
                (entry for entry in entries if entry.category == category),
                key=lambda entry: entry.last_accessed,
            )
            size = sum(entry.size for entry in category_entries)
            for entry in category_entries:
                if size <= quota:
                    break
                selected[entry.path] = entry
                size -= entry.size
        remaining = [entry for entry in entries if entry.path not in selected]
        total = sum(entry.size for entry in remaining)
        for entry in sorted(remaining, key=lambda item: item.last_accessed):
            if total <= self.total_quota:
                break
            selected[entry.path] = entry
            total -= entry.size
        return self._delete_entries(list(selected.values()))

    def clean_suggestions(self) -> dict[str, int]:
        return self.clean_category("suggestions")

    def clean_category(self, category: str) -> dict[str, int]:
        if category not in self._roots():
            raise ValueError("unknown cache category")
        return self._delete_entries([
            entry for entry in self._scan() if entry.category == category
        ])

    def clean_all(self) -> dict[str, int]:
        return self._delete_entries(self._scan())

    def _safe_candidate(self, path: Path) -> Path:
        candidate = Path(path).expanduser()
        resolved = candidate.resolve(strict=True)
        cache_home = self.paths.cache_home.resolve()
        allowed_roots = [root.resolve() for roots in self._roots().values() for root in roots]
        if cache_home not in resolved.parents:
            raise CacheSafetyError("path is outside the cache")
        if not any(resolved == root or root in resolved.parents for root in allowed_roots):
            raise CacheSafetyError("path is outside managed cache categories")
        if any(resolved == root or root in resolved.parents for root in self.library_roots):
            raise CacheSafetyError("refusing to delete a Library path")
        return candidate

    def _delete_entries(self, entries: list[CacheEntry]) -> dict[str, int]:
        removed = 0
        reclaimed = 0
        for entry in entries:
            path = self.paths.cache_home / entry.path
            try:
                safe = self._safe_candidate(path)
                safe.unlink()
            except FileNotFoundError:
                continue
            removed += 1
            reclaimed += entry.size
        return {"removed": removed, "reclaimed": reclaimed}

    def _atomic_write(self, data: dict[str, Any]) -> None:
        self.paths.cache_home.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.paths.cache_home,
                prefix=f".{INDEX_FILENAME}-", delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(0o600)
            os.replace(temporary, self.index_file)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
