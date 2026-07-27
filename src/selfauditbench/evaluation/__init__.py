"""Replay execution, annotation, metrics, and reporting."""

from typing import Any

__all__ = ["ReplayRunner", "aggregate_metrics"]


def __getattr__(name: str) -> Any:
    if name == "ReplayRunner":
        from selfauditbench.evaluation.runner import ReplayRunner

        return ReplayRunner
    if name == "aggregate_metrics":
        from selfauditbench.evaluation.metrics import aggregate_metrics

        return aggregate_metrics
    raise AttributeError(name)
