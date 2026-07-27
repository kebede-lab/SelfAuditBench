#!/usr/bin/env python3
"""Probe CSTCloud model listing and chat completions without printing secrets."""

from __future__ import annotations

import os
import sys

from openai import OpenAI

DEFAULT_BASE_URL = "https://uni-api.cstcloud.cn/v1"
DEFAULT_MODEL = "deepseek-v4-flash"


def main() -> None:
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    base_url = (
        os.getenv("AGENTFORESIGHT_BASE_URL")
        or os.getenv("BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("OPENAI_API_BASE")
        or DEFAULT_BASE_URL
    )
    model = os.getenv("AGENTFORESIGHT_MODEL") or os.getenv("MODEL_NAME") or DEFAULT_MODEL

    print(f"base_url={base_url}")
    print(f"model={model}")
    if not api_key:
        print("ERROR: OPENAI_API_KEY/DEEPSEEK_API_KEY is not set in the current shell.", file=sys.stderr)
        raise SystemExit(2)

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=60, max_retries=2)
    try:
        models = client.models.list()
        ids = [item.id for item in models.data]
        print("models_list_ok=1")
        print("available_models=" + ",".join(ids[:50]))
        if model not in ids:
            print(f"WARNING: AGENTFORESIGHT_MODEL '{model}' was not in the first {min(50, len(ids))} listed models.")
    except Exception as exc:
        print(f"models_list_ok=0 ({type(exc).__name__}: {str(exc)[:180]})")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply exactly: agentforesight cstcloud ok"}],
            temperature=0,
            max_tokens=20,
        )
    except Exception as exc:
        print(f"chat_ok=0 ({type(exc).__name__}: {str(exc)[:500]})", file=sys.stderr)
        raise SystemExit(1) from exc
    print("chat_ok=1")
    print("reply=" + (response.choices[0].message.content or "").strip())


if __name__ == "__main__":
    main()
