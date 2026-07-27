"""Remove hidden reasoning from auditor-visible trajectory state."""

from __future__ import annotations

import re
from typing import Any

TAGGED_PRIVATE_BLOCKS = re.compile(
    r"<(?:scratch_pad|think|thought_assess|thought_plan_next)>.*?</(?:scratch_pad|think|thought_assess|thought_plan_next)>",
    flags=re.DOTALL | re.IGNORECASE,
)
ASB_THINKING = re.compile(
    r"\[Thinking\]:.*?(?=(?:\[Action\]:|\[Observation\]:|$))",
    flags=re.DOTALL | re.IGNORECASE,
)


def strip_hidden_reasoning(text: str) -> str:
    """Strip benchmark-private reasoning while retaining observable action text."""

    text = TAGGED_PRIVATE_BLOCKS.sub("[hidden_reasoning_removed]", text)
    text = ASB_THINKING.sub("[hidden_reasoning_removed]", text)
    return text.strip()


def sanitize_payload(value: Any) -> Any:
    """Recursively sanitize raw adapter payloads before they reach an auditor."""

    if isinstance(value, str):
        return strip_hidden_reasoning(value)
    if isinstance(value, dict):
        return {str(key): sanitize_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_payload(item) for item in value)
    return value
