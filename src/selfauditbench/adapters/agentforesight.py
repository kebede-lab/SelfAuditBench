"""Replay adapter for the official AgentForesight AFTraj-2K parquet artifacts."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from selfauditbench.adapters.common import REPLAY_TIMESTAMP, relative_ref, slug, stable_id
from selfauditbench.core.models import (
    ActionType,
    CapabilityGrant,
    Checkpoint,
    EventKind,
    LabelProvenance,
    PermissionState,
    Provenance,
    Scenario,
    ScenarioLabel,
    Sensitivity,
    TrajectoryEvent,
)
from selfauditbench.core.sanitize import sanitize_payload


class AFTrajDependencyError(RuntimeError):
    """Raised when parquet ingestion dependencies are unavailable."""


class AFTrajReplayAdapter:
    """Normalize AFTraj-2K rows while preserving decisive-error step indices."""

    source_dataset = "agentforesight"

    def __init__(
        self,
        domains: Iterable[str] | None = None,
        paper_test_split: bool = False,
    ) -> None:
        self._domains = set(domains) if domains is not None else None
        self._paper_test_split = paper_test_split

    def load(self, source: Path) -> Iterable[Scenario]:
        """Load an AFTraj directory or one official parquet split."""

        if source.is_dir():
            paths = [
                ("safe", source / "aftraj_safe.parquet"),
                ("unsafe", source / "aftraj_unsafe.parquet"),
            ]
            root = source
        else:
            split = self._split_from_filename(source)
            paths = [(split, source)]
            root = source.parent

        test_ids = self._load_test_ids(root) if self._paper_test_split else None
        for split, path in paths:
            if not path.exists():
                raise FileNotFoundError(f"missing official AFTraj parquet artifact: {path}")
            yield from self._load_parquet(path, root, split, test_ids)

    def _load_parquet(
        self,
        path: Path,
        root: Path,
        split: str,
        test_ids: dict[str, set[str]] | None,
    ) -> Iterator[Scenario]:
        try:
            import pandas as pd  # type: ignore[import-untyped]
        except ImportError as exc:
            raise AFTrajDependencyError(
                "AFTraj parquet ingestion requires `pip install -e .[agentforesight]`."
            ) from exc

        try:
            frame = pd.read_parquet(path)
        except ImportError as exc:
            raise AFTrajDependencyError(
                "AFTraj parquet ingestion requires a parquet engine. "
                "Install `pip install -e .[agentforesight]`."
            ) from exc

        for row_number, (_, row) in enumerate(frame.iterrows(), start=1):
            value = row.to_dict()
            conv_id = str(value.get("conv_id", ""))
            if self._domains is not None and str(value.get("domain", "")) not in self._domains:
                continue
            if test_ids is not None and conv_id not in test_ids[split]:
                continue
            yield self.scenario_from_row(value, split, path, root, row_number)

    def scenario_from_row(
        self,
        row: dict[str, Any],
        split: str,
        path: Path,
        root: Path,
        row_number: int,
    ) -> Scenario:
        """Normalize one official row; public to support fixture-based verification."""

        conv_id = str(row["conv_id"])
        raw_ref = f"{relative_ref(path, root)}#row={row_number}"
        scenario_id = stable_id("agentforesight", split, conv_id)
        turns = self._as_mapping_list(row.get("turns"))
        tools = self._as_mapping_list(row.get("tools"))
        events = tuple(
            self._turn_event(scenario_id, index, turn, raw_ref)
            for index, turn in enumerate(turns)
        )

        risky = split == "unsafe"
        mistake_step = int(row.get("mistake_step", -1))
        decisive_step = mistake_step if risky and mistake_step >= 0 else None
        label = ScenarioLabel(
            risky=risky,
            first_risk_sufficient_event=decisive_step,
            harm_boundary_event=None,
            accepted_interventions=(),
            utility_expectation=(
                "Alarm at the earliest observable decisive error while preserving "
                "safe trajectories."
            ),
        )
        grants = {
            f"tool:{slug(str(tool['name']))}": CapabilityGrant(
                capability=f"tool:{slug(str(tool['name']))}",
                operations=(ActionType.TOOL_CALL.value,),
            )
            for tool in tools
            if tool.get("name")
        }
        tags = tuple(
            sorted(
                {
                    "curated-label",
                    f"domain:{slug(str(row.get('domain', 'unknown')))}",
                    f"split:{split}",
                    *(
                        [f"unsafe-source:{slug(str(row['unsafe_source']))}"]
                        if row.get("unsafe_source")
                        else []
                    ),
                }
            )
        )
        return Scenario(
            scenario_id=scenario_id,
            source_dataset=self.source_dataset,
            source_ref=raw_ref,
            tags=tags,
            weak_label=False,
            label_provenance=LabelProvenance.SOURCE_CURATED,
            initial_permissions=PermissionState(grants=grants),
            events=events,
            label=label,
        )

    @staticmethod
    def _turn_event(
        scenario_id: str,
        index: int,
        turn: dict[str, Any],
        raw_ref: str,
    ) -> TrajectoryEvent:
        role = str(turn.get("role", "unknown"))
        visible_turn = {key: value for key, value in turn.items() if key != "thought"}
        if turn.get("thought"):
            visible_turn["hidden_reasoning_present"] = True
        return TrajectoryEvent(
            event_id=f"{scenario_id}:event:{index}",
            scenario_id=scenario_id,
            sequence=index,
            event_kind=EventKind.MESSAGE,
            source=AFTrajReplayAdapter._provenance(role),
            checkpoint=Checkpoint.POST_MESSAGE,
            sensitivity=Sensitivity.INTERNAL,
            visible_payload=sanitize_payload(visible_turn),
            raw_artifact_ref=raw_ref,
            created_at=REPLAY_TIMESTAMP,
        )

    @staticmethod
    def _provenance(role: str) -> Provenance:
        normalized = role.lower()
        if normalized == "user":
            return Provenance.USER
        if any(token in normalized for token in ("tool", "environment", "executor")):
            return Provenance.TOOL
        if normalized in {"system", "controller"}:
            return Provenance.CONTROLLER
        return Provenance.AGENT

    @staticmethod
    def _as_mapping_list(value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        if hasattr(value, "tolist"):
            value = value.tolist()
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, (list, tuple)):
            raise ValueError("AFTraj turns and tools must be list-like")
        if not all(isinstance(item, dict) for item in value):
            raise ValueError("AFTraj turns and tools must contain mappings")
        return [dict(item) for item in value]

    @staticmethod
    def _split_from_filename(path: Path) -> str:
        if path.name == "aftraj_safe.parquet":
            return "safe"
        if path.name == "aftraj_unsafe.parquet":
            return "unsafe"
        raise ValueError(
            "AFTraj parquet file must be named aftraj_safe.parquet or aftraj_unsafe.parquet"
        )

    @staticmethod
    def _load_test_ids(root: Path) -> dict[str, set[str]]:
        path = root / "splits_test.json"
        if not path.exists():
            raise FileNotFoundError(f"paper test split requested but missing: {path}")
        value = json.loads(path.read_text(encoding="utf-8"))
        return {
            "safe": set(value["test_safe"]),
            "unsafe": set(value["test_unsafe"]),
        }
