"""Scenario JSONL input and output."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from selfauditbench.core.models import Scenario
from selfauditbench.storage.hashing import canonical_json


def write_scenarios(path: Path, scenarios: Iterable[Scenario]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    count = 0
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            for scenario in scenarios:
                handle.write(canonical_json(scenario.model_dump(mode="json")) + "\n")
                count += 1
        temporary.replace(path)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return count


def read_scenarios(path: Path) -> list[Scenario]:
    scenarios: list[Scenario] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                scenarios.append(Scenario.model_validate(json.loads(line)))
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"invalid scenario at {path}:{line_number}: {exc}") from exc
    return scenarios
