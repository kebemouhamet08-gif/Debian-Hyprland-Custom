"""Explicit, backup-first migrations for legacy metadata and recommendations."""

from __future__ import annotations

from pathlib import Path
import shutil
import sqlite3

from .library import Library


def migrate_legacy_metadata(
    library: Library,
    roots,
    legacy_metadata: Path,
) -> dict[str, object]:
    """Populate Library progressively while retaining the legacy JSON as backup."""
    legacy_metadata = Path(legacy_metadata)
    backup = legacy_metadata.with_name(legacy_metadata.name + ".v1.backup")
    if legacy_metadata.is_file() and not backup.exists():
        shutil.copy2(legacy_metadata, backup)
    result = library.scan(roots)
    return {
        **result,
        "legacy_preserved": legacy_metadata.is_file(),
        "backup": str(backup) if backup.exists() else None,
    }


def preserve_recommendations(legacy_database: Path, destination: Path) -> dict[str, object]:
    """Copy a valid legacy SQLite DB with SQLite's online backup API."""
    legacy_database = Path(legacy_database)
    destination = Path(destination)
    if destination.exists():
        return {"copied": False, "reason": "destination exists"}
    if not legacy_database.is_file():
        return {"copied": False, "reason": "legacy database missing"}
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".new")
    source = target = None
    try:
        source = sqlite3.connect(f"file:{legacy_database}?mode=ro", uri=True)
        source.execute("PRAGMA quick_check").fetchone()
        target = sqlite3.connect(temporary)
        source.backup(target)
        target.close()
        target = None
        check = sqlite3.connect(f"file:{temporary}?mode=ro", uri=True)
        try:
            status = check.execute("PRAGMA quick_check").fetchone()[0]
            count = check.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        finally:
            check.close()
        if status != "ok":
            raise sqlite3.DatabaseError(status)
        temporary.chmod(0o600)
        temporary.replace(destination)
        return {"copied": True, "candidates": count}
    finally:
        if target is not None:
            target.close()
        if source is not None:
            source.close()
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
