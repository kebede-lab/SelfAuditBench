"""Shared adapter helpers."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from selfauditbench.storage.hashing import sha256_json

REPLAY_TIMESTAMP = datetime(1970, 1, 1, tzinfo=UTC)


def stable_id(prefix: str, *parts: object) -> str:
    return f"{prefix}-{sha256_json([str(part) for part in parts])[:16]}"


def relative_ref(path: Path, source_root: Path) -> str:
    try:
        return path.resolve().relative_to(source_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip())
    return normalized.strip("-").lower() or "unknown"

