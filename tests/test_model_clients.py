from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from selfauditbench.actors.clients import OpenAICompatibleModelClient
from selfauditbench.config import load_closed_loop_config, load_run_config
from selfauditbench.core.models import ModelProfile

ROOT = Path(__file__).parents[1]


class _FakeCompletions:
    def __init__(self, content: str = '{"ok": true}') -> None:
        self.calls: list[dict[str, Any]] = []
        self.content = content

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))],
            usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5),
        )


def _client(
    profile: ModelProfile,
    *,
    content: str = '{"ok": true}',
) -> tuple[OpenAICompatibleModelClient, _FakeCompletions]:
    completions = _FakeCompletions(content)
    value = object.__new__(OpenAICompatibleModelClient)
    value._profile = profile
    value._client = cast(
        Any,
        SimpleNamespace(chat=SimpleNamespace(completions=completions)),
    )
    value._last_call_usage = {}
    return value, completions


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        (
            ModelProfile(
                provider="deepseek-openai-compatible",
                model="deepseek-v4-flash",
                thinking_mode="disabled",
            ),
            {"extra_body": {"thinking": {"type": "disabled"}}},
        ),
        (
            ModelProfile(
                provider="ollama-openai-compatible",
                model="gemma4:12b",
                thinking_mode="disabled",
            ),
            {"reasoning_effort": "none"},
        ),
        (
            ModelProfile(
                provider="qwen-openai-compatible",
                model="qwen3.5",
                thinking_mode="disabled",
            ),
            {"extra_body": {"enable_thinking": False}},
        ),
    ],
)
def test_openai_compatible_client_maps_thinking_controls(
    profile: ModelProfile,
    expected: dict[str, Any],
) -> None:
    client, completions = _client(profile)

    assert client.complete_text([{"role": "user", "content": "Return JSON."}])

    call = completions.calls[0]
    assert call.get("extra_body") == expected.get("extra_body")
    assert call.get("reasoning_effort") == expected.get("reasoning_effort")


def test_openai_compatible_client_rejects_unmapped_thinking_control() -> None:
    profile = ModelProfile(
        provider="openai-compatible",
        model="unknown-thinking-model",
        thinking_mode="disabled",
    )
    client, _ = _client(profile)

    with pytest.raises(ValueError, match="not mapped for provider"):
        client.complete_text([{"role": "user", "content": "Return JSON."}])


def test_openai_compatible_client_preflight_rejects_empty_content() -> None:
    profile = ModelProfile(provider="openai-compatible", model="empty-model")
    client, _ = _client(profile, content="")

    with pytest.raises(ValueError, match="preflight returned an empty response"):
        client.preflight()


def test_final_deepseek_and_gemma_configs_disable_thinking() -> None:
    paths = sorted((ROOT / "configs").glob("*gold-deepseek*.yaml")) + sorted(
        (ROOT / "configs").glob("*gold-ollama-gemma4*.yaml")
    )

    assert len(paths) == 16
    for path in paths:
        if "closed-loop" in path.name:
            config = load_closed_loop_config(path)
            profiles = [config.model, config.recovery_model]
        else:
            profiles = [load_run_config(path).model]
        selected = [profile for profile in profiles if profile is not None]
        assert all(profile.thinking_mode == "disabled" for profile in selected)
        if "deepseek" in path.name:
            assert all(profile.provider == "deepseek-openai-compatible" for profile in selected)
            assert all(profile.base_url == "https://api.deepseek.com" for profile in selected)
        else:
            assert all(profile.provider == "ollama-openai-compatible" for profile in selected)


def test_agentforesight_hosted_configs_use_official_deepseek_without_thinking() -> None:
    paths = [
        ROOT / "configs" / "agentforesight-official-deepseek-smoke.yaml",
        ROOT / "configs" / "agentforesight-official-deepseek-sidecar.yaml",
    ]

    for path in paths:
        profile = load_run_config(path).model
        assert profile is not None
        assert profile.provider == "deepseek-openai-compatible"
        assert profile.base_url == "https://api.deepseek.com"
        assert profile.api_key_env == "DEEPSEEK_API_KEY"
        assert profile.thinking_mode == "disabled"


def test_all_qwen_configs_disable_thinking() -> None:
    paths = sorted((ROOT / "configs").glob("*qwen35*.yaml")) + sorted(
        (ROOT / "configs").glob("*closed-loop*.yaml")
    )

    assert paths
    for path in paths:
        if "closed-loop" in path.name:
            profiles = [load_closed_loop_config(path).outcome_judge_model]
        else:
            profiles = [load_run_config(path).model]
        selected = [profile for profile in profiles if profile is not None]
        assert selected
        assert all(profile.provider == "qwen-openai-compatible" for profile in selected)
        assert all(profile.api_key_env == "QWEN_API_KEY" for profile in selected)
        assert all(profile.thinking_mode == "disabled" for profile in selected)


def test_closed_loop_recovery_configs_allow_complete_canonical_actions() -> None:
    paths = sorted((ROOT / "configs").glob("*closed-loop*.yaml"))

    assert len(paths) == 8
    for path in paths:
        config = load_closed_loop_config(path)
        assert config.recovery_model.max_tokens == 2400
