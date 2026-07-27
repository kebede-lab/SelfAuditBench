"""YAML configuration for reproducible benchmark runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, model_validator

from selfauditbench.core.models import (
    AuditEmissionMode,
    ClosedLoopCondition,
    FrozenModel,
    ModelProfile,
    StrategyId,
)


class RunConfig(FrozenModel):
    run_id: str
    strategy: StrategyId
    audit_mode: AuditEmissionMode
    dataset: Path
    output_root: Path = Path("artifacts/runs")
    random_seed: int = 0
    fail_closed: bool = True
    model: ModelProfile | None = None
    observer_model: ModelProfile | None = None


class ClosedLoopConfig(RunConfig):
    """Configuration for normalized enacted recovery experiments."""

    condition: ClosedLoopCondition
    recovery_model: ModelProfile
    outcome_judge_model: ModelProfile
    max_replans: int = Field(default=3, ge=1, le=20)
    max_recovery_steps: int = Field(default=6, ge=1, le=50)
    driver_id: str = "normalized_action_sink"

    @model_validator(mode="after")
    def condition_matches_audit_mode(self) -> ClosedLoopConfig:
        expected = (
            AuditEmissionMode.SIDECAR
            if self.condition == ClosedLoopCondition.SIDECAR_RECOVERY
            else AuditEmissionMode.INLINE
        )
        if self.audit_mode != expected:
            raise ValueError(
                f"condition {self.condition.value} requires audit_mode={expected.value}"
            )
        if self.strategy != StrategyId.SELF_AUDIT_BROKER:
            raise ValueError("closed-loop conditions require strategy=self_audit_broker")
        if self.condition == ClosedLoopCondition.SIDECAR_RECOVERY and self.model is None:
            raise ValueError("sidecar_recovery requires the sidecar audit model")
        return self


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected a YAML mapping in {path}")
    return value


def load_run_config(path: Path) -> RunConfig:
    value = load_yaml(path)
    config = RunConfig.model_validate(value)
    base = path.parent
    return config.model_copy(
        update={
            "dataset": (base / config.dataset).resolve(),
            "output_root": (base / config.output_root).resolve(),
        }
    )


def load_closed_loop_config(path: Path) -> ClosedLoopConfig:
    value = load_yaml(path)
    config = ClosedLoopConfig.model_validate(value)
    base = path.parent
    return config.model_copy(
        update={
            "dataset": (base / config.dataset).resolve(),
            "output_root": (base / config.output_root).resolve(),
        }
    )


class IngestConfig(FrozenModel):
    source: Path
    destination: Path
    limit: int | None = Field(default=None, ge=1)
