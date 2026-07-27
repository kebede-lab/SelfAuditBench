"""Replay normalizers and immutable live bridges for supported benchmarks."""

from typing import Any

__all__ = [
    "AFTrajReplayAdapter",
    "ASBLiveBridge",
    "ASBReplayAdapter",
    "ConVerseLiveBridge",
    "ConVerseReplayAdapter",
    "load_agentforesight_reproduction_results",
    "write_agentforesight_reproduction_run",
]


def __getattr__(name: str) -> Any:
    if name == "AFTrajReplayAdapter":
        from selfauditbench.adapters.agentforesight import AFTrajReplayAdapter

        return AFTrajReplayAdapter
    if name == "ASBReplayAdapter":
        from selfauditbench.adapters.asb import ASBReplayAdapter

        return ASBReplayAdapter
    if name == "ConVerseReplayAdapter":
        from selfauditbench.adapters.converse import ConVerseReplayAdapter

        return ConVerseReplayAdapter
    if name in {"ASBLiveBridge", "ConVerseLiveBridge"}:
        from selfauditbench.adapters.live import ASBLiveBridge, ConVerseLiveBridge

        return {
            "ASBLiveBridge": ASBLiveBridge,
            "ConVerseLiveBridge": ConVerseLiveBridge,
        }[name]
    if name in {
        "load_agentforesight_reproduction_results",
        "write_agentforesight_reproduction_run",
    }:
        from selfauditbench.adapters.agentforesight_results import (
            load_agentforesight_reproduction_results,
            write_agentforesight_reproduction_run,
        )

        return {
            "load_agentforesight_reproduction_results": (
                load_agentforesight_reproduction_results
            ),
            "write_agentforesight_reproduction_run": write_agentforesight_reproduction_run,
        }[name]
    raise AttributeError(name)
