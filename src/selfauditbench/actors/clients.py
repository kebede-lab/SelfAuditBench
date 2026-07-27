"""Live OpenAI-compatible and deterministic scripted model clients."""

from __future__ import annotations

import json
import os
from collections import deque
from collections.abc import Iterable, Sequence
from math import ceil
from time import perf_counter
from typing import Any

from openai import OpenAI

from selfauditbench.core.models import ModelProfile


class OpenAICompatibleModelClient:
    """Small provider-neutral JSON client for OpenAI-compatible endpoints."""

    def __init__(self, profile: ModelProfile, api_key_env: str | None = None) -> None:
        selected_env = api_key_env or profile.api_key_env
        api_key = os.getenv(selected_env)
        if not api_key:
            raise ValueError(f"missing API key environment variable {selected_env}")
        self._profile = profile
        self._client = OpenAI(
            api_key=api_key,
            base_url=profile.base_url,
            timeout=profile.timeout_seconds,
            max_retries=profile.max_retries,
        )
        self._last_call_usage: dict[str, Any] = {}

    @property
    def profile(self) -> ModelProfile:
        return self._profile

    def complete_text(
        self,
        messages: Sequence[dict[str, str]],
        *,
        json_mode: bool = True,
        max_tokens_override: int | None = None,
    ) -> str:
        # Compatible providers accept deployment names beyond OpenAI's typed literals.
        prompt_tokens_estimated = _estimate_messages_tokens(messages)
        kwargs: dict[str, Any] = {
            "model": self._profile.model,
            "messages": list(messages),
        }
        if self._profile.temperature is not None:
            kwargs["temperature"] = self._profile.temperature
        max_tokens = (
            max_tokens_override if max_tokens_override is not None else self._profile.max_tokens
        )
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        kwargs.update(_thinking_request_kwargs(self._profile))
        started = perf_counter()
        try:
            response = self._client.chat.completions.create(
                **kwargs,
            )
        except Exception:
            self._last_call_usage = self._usage_record(
                perf_counter() - started,
                prompt_tokens_estimated=prompt_tokens_estimated,
            )
            raise
        duration = perf_counter() - started
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None) if usage is not None else None
        completion_tokens = getattr(usage, "completion_tokens", None) if usage is not None else None
        total_tokens = getattr(usage, "total_tokens", None) if usage is not None else None
        content = response.choices[0].message.content or ""
        completion_tokens_estimated = _estimate_text_tokens(content)
        self._last_call_usage = self._usage_record(
            duration,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            prompt_tokens_estimated=prompt_tokens_estimated,
            completion_tokens_estimated=completion_tokens_estimated,
        )
        return content

    def last_call_usage(self) -> dict[str, Any]:
        return dict(self._last_call_usage)

    def preflight(self) -> None:
        """Make a minimal call to verify token, model, and endpoint reachability."""

        content = self.complete_text(
            [
                {
                    "role": "system",
                    "content": "Reply exactly with OK.",
                },
                {"role": "user", "content": "SelfAuditBench API preflight."},
            ],
            json_mode=False,
            max_tokens_override=16,
        )
        if not content.strip():
            raise ValueError("model preflight returned an empty response")

    def complete_json(self, messages: Sequence[dict[str, str]]) -> dict[str, Any]:
        content = self.complete_text(messages, json_mode=True)
        return parse_json_object(
            content,
            empty_message="model returned an empty JSON response",
        )

    def _usage_record(
        self,
        duration_seconds: float,
        *,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        prompt_tokens_estimated: int | None = None,
        completion_tokens_estimated: int | None = None,
    ) -> dict[str, Any]:
        total_tokens_estimated = _sum_estimated_tokens(
            prompt_tokens_estimated,
            completion_tokens_estimated,
        )
        return {
            "provider": self._profile.provider,
            "model": self._profile.model,
            "duration_seconds": duration_seconds,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "prompt_tokens_estimated": prompt_tokens_estimated,
            "completion_tokens_estimated": completion_tokens_estimated,
            "total_tokens_estimated": total_tokens_estimated,
            "token_accounting": (
                "provider_usage"
                if total_tokens is not None
                else "local_estimate"
                if total_tokens_estimated is not None
                else "none"
            ),
            "estimated_cost_usd": _estimate_cost(
                self._profile,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            ),
        }


class ScriptedModelClient:
    """Queue-backed model double for deterministic tests and smoke examples."""

    def __init__(self, responses: Iterable[dict[str, Any] | str]) -> None:
        self._responses = deque(responses)
        self.messages: list[Sequence[dict[str, str]]] = []
        self._last_call_usage: dict[str, Any] = {}

    def complete_text(
        self,
        messages: Sequence[dict[str, str]],
        *,
        json_mode: bool = True,
        max_tokens_override: int | None = None,
    ) -> str:
        del json_mode, max_tokens_override
        self.messages.append(messages)
        if not self._responses:
            raise RuntimeError("scripted model client has no remaining response")
        response = self._responses.popleft()
        content = json.dumps(response, sort_keys=True) if isinstance(response, dict) else response
        prompt_tokens_estimated = _estimate_messages_tokens(messages)
        completion_tokens_estimated = _estimate_text_tokens(content)
        self._last_call_usage = {
            "provider": "scripted",
            "model": "scripted",
            "duration_seconds": 0.0,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "prompt_tokens_estimated": prompt_tokens_estimated,
            "completion_tokens_estimated": completion_tokens_estimated,
            "total_tokens_estimated": _sum_estimated_tokens(
                prompt_tokens_estimated,
                completion_tokens_estimated,
            ),
            "token_accounting": "local_estimate",
            "estimated_cost_usd": None,
        }
        return content

    def last_call_usage(self) -> dict[str, Any]:
        return dict(self._last_call_usage)

    def preflight(self) -> None:
        self.complete_json([{"role": "user", "content": "SelfAuditBench API preflight."}])

    def complete_json(self, messages: Sequence[dict[str, str]]) -> dict[str, Any]:
        content = self.complete_text(messages, json_mode=True)
        return parse_json_object(
            content,
            empty_message="model returned an empty JSON response",
        )


def parse_json_object(content: str, *, empty_message: str) -> dict[str, Any]:
    """Extract one JSON object from a provider response.

    OpenAI-compatible providers occasionally wrap an otherwise valid JSON object
    in Markdown fences or short explanatory text despite JSON response mode.  All
    model-backed components use this bounded extractor before schema validation so
    provider presentation does not become a semantic evaluation failure.
    """
    if not content:
        raise ValueError(empty_message)
    first_error: json.JSONDecodeError | None = None
    for candidate in _json_object_candidates(content.strip()):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            first_error = first_error or exc
            continue
        if isinstance(parsed, dict):
            return parsed
    if first_error is not None:
        raise first_error
    raise ValueError("model JSON response must contain a JSON object")


def _json_object_candidates(text: str) -> Iterable[str]:
    yield text
    start: int | None = None
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                yield text[start : index + 1]
                start = None


def _thinking_request_kwargs(profile: ModelProfile) -> dict[str, Any]:
    if profile.thinking_mode == "default":
        return {}
    if profile.provider == "ollama-openai-compatible":
        effort = "none" if profile.thinking_mode == "disabled" else "high"
        return {"reasoning_effort": effort}
    if profile.provider == "deepseek-openai-compatible":
        return {"extra_body": {"thinking": {"type": profile.thinking_mode}}}
    if profile.provider == "qwen-openai-compatible":
        return {"extra_body": {"enable_thinking": profile.thinking_mode == "enabled"}}
    raise ValueError(
        f"thinking_mode={profile.thinking_mode!r} is not mapped for provider {profile.provider!r}"
    )


def _estimate_cost(
    profile: ModelProfile,
    *,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> float | None:
    cost = 0.0
    priced = False
    if prompt_tokens is not None and profile.input_cost_per_million_tokens_usd is not None:
        cost += prompt_tokens * profile.input_cost_per_million_tokens_usd / 1_000_000
        priced = True
    if completion_tokens is not None and profile.output_cost_per_million_tokens_usd is not None:
        cost += completion_tokens * profile.output_cost_per_million_tokens_usd / 1_000_000
        priced = True
    return cost if priced else None


def _estimate_messages_tokens(messages: Sequence[dict[str, str]]) -> int:
    serialized = "\n".join(
        f"{message.get('role', '')}: {message.get('content', '')}" for message in messages
    )
    return _estimate_text_tokens(serialized)


def _estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, ceil(len(text) / 4))


def _sum_estimated_tokens(*values: int | None) -> int | None:
    present = [value for value in values if value is not None]
    return sum(present) if present else None
