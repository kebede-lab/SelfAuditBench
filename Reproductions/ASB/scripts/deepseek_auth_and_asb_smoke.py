#!/usr/bin/env python3
"""DeepSeek/OpenAI-compatible authentication + ASB one-record smoke test.

This script intentionally never prints API keys. It checks:
1) env/config used by the current shell,
2) a raw OpenAI-compatible chat completion,
3) a raw tool-calling completion (ASB sends tools=...), and
4) one minimal ASB attack record using data/*_test.jsonl.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def mask_bool(name: str) -> str:
    return "set" if os.getenv(name) else "missing"


def choose_defaults() -> tuple[str, str]:
    base_url = (
        os.getenv("BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("OPENAI_API_BASE")
        or "https://api.deepseek.com/v1"
    )
    model = os.getenv("ASB_MODEL") or os.getenv("MODEL_NAME") or os.getenv("OPENAI_MODEL")
    if not model:
        model = "deepseek-v4-flash"
    return base_url, model


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)

    base_url, model = choose_defaults()
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")

    print("== ASB DeepSeek auth/config smoke ==")
    print("cwd=", root)
    print("python=", sys.executable)
    print("started=", datetime.now().isoformat(timespec="seconds"))
    print("OPENAI_API_KEY=", mask_bool("OPENAI_API_KEY"))
    print("DEEPSEEK_API_KEY=", mask_bool("DEEPSEEK_API_KEY"))
    print("BASE_URL=", base_url)
    print("ASB_MODEL=", model)
    print("ASB_JUDGE_MODEL=", os.getenv("ASB_JUDGE_MODEL") or model)

    if not api_key:
        print("FAIL: neither OPENAI_API_KEY nor DEEPSEEK_API_KEY is set in this shell.", file=sys.stderr)
        return 2

    try:
        from openai import OpenAI
    except Exception as exc:
        print(f"FAIL: cannot import openai package in this Python: {exc!r}", file=sys.stderr)
        return 3

    client = OpenAI(api_key=api_key, base_url=base_url)

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply exactly: asb deepseek ok"}],
            max_tokens=20,
            temperature=0,
        )
        print("raw_chat_ok=1")
        print("raw_chat_reply=", (resp.choices[0].message.content or "").strip())
    except Exception as exc:
        print(f"FAIL: raw chat call failed: {type(exc).__name__}: {str(exc)[:600]}", file=sys.stderr)
        return 4

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Use the tool if available, otherwise say no tool."}],
            tools=[{
                "type": "function",
                "function": {
                    "name": "smoke_tool",
                    "description": "A no-op smoke-test tool.",
                    "parameters": {
                        "type": "object",
                        "properties": {"status": {"type": "string"}},
                        "required": ["status"],
                    },
                },
            }],
            max_tokens=40,
            temperature=0,
        )
        msg = resp.choices[0].message
        print("raw_tools_param_ok=1")
        print("raw_tools_tool_calls=", bool(getattr(msg, "tool_calls", None)))
    except Exception as exc:
        print(f"FAIL: tools= parameter failed: {type(exc).__name__}: {str(exc)[:600]}", file=sys.stderr)
        return 5

    smoke_dir = root / "logs" / "_smoke"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    csv_path = smoke_dir / f"asb_one_record_{model.replace('/', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    log_path = csv_path.with_suffix(".log")

    env = os.environ.copy()
    env.update({
        "OPENAI_API_KEY": api_key,
        "BASE_URL": base_url,
        "OPENAI_BASE_URL": base_url,
        "OPENAI_API_BASE": base_url,
        "ASB_MODEL": model,
        "ASB_JUDGE_MODEL": os.getenv("ASB_JUDGE_MODEL") or model,
        "ASB_MAX_WORKERS": "1",
        "ASB_EMBEDDING_BACKEND": os.getenv("ASB_EMBEDDING_BACKEND", "ollama"),
        "ASB_EMBEDDING_MODEL": os.getenv("ASB_EMBEDDING_MODEL", "nomic-embed-text"),
        "ASB_MEMORY_DB_SUFFIX": os.getenv("ASB_MEMORY_DB_SUFFIX", os.getenv("ASB_EMBEDDING_MODEL", "nomic-embed-text")),
    })

    cmd = [
        sys.executable,
        "main_attacker.py",
        "--llm_name", model,
        "--attack_type", "combined_attack",
        "--use_backend", "None",
        "--attacker_tools_path", "data/attack_tools_test.jsonl",
        "--tasks_path", "data/agent_task_test.jsonl",
        "--task_num", "1",
        "--res_file", str(csv_path),
        "--database", f"memory_db/direct_prompt_injection/combined_attack_{env['ASB_MEMORY_DB_SUFFIX'].replace('/', '_')}",
        "--clean",
        "--defense_type", "dynamic_prompt_rewriting",
        "--max_new_tokens", "128",
    ]
    print("running_asb_one_record=", " ".join(cmd))
    with log_path.open("w", encoding="utf-8", errors="ignore") as log_f:
        try:
            result = subprocess.run(cmd, env=env, stdout=log_f, stderr=subprocess.STDOUT, timeout=420)
        except subprocess.TimeoutExpired:
            print("FAIL: ASB one-record smoke timed out after 420s")
            print("asb_log=", log_path)
            return 6

    print("asb_exit_code=", result.returncode)
    print("asb_log=", log_path)
    print("asb_csv=", csv_path)
    if result.returncode != 0:
        print("FAIL: ASB one-record subprocess failed; inspect the log above.", file=sys.stderr)
        return 7

    rows = csv_path.read_text(errors="ignore").splitlines() if csv_path.exists() else []
    print("asb_csv_lines=", len(rows))
    if len(rows) < 2:
        print("FAIL: ASB exited successfully but did not write a result row.", file=sys.stderr)
        return 8

    print("PASS: raw auth, tool parameter compatibility, and one ASB result row all worked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
