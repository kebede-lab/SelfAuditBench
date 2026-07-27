#!/usr/bin/env python3
import os
import sys
import time
from pathlib import Path
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from assistant.assistant_prompts import (
    get_aggregated_prompts_for_planning_naive,
    initial_plan_delimiter,
    start_plan_prompt,
)
from assistant.assistant_utils import extract_output
from use_cases.data_loader import (
    get_external_agent_role_for_use_case,
    load_persona_data_for_use_case,
)

base_url = os.getenv("BASE_URL") or os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE") or "https://uni-api.cstcloud.cn/v1"
model = os.getenv("CONVERSE_MODEL") or os.getenv("MODEL_NAME") or "deepseek-v4-flash"
api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")

print(f"base_url={base_url}")
print(f"model={model}")

if not api_key:
    print("ERROR: OPENAI_API_KEY/DEEPSEEK_API_KEY is not set in the current shell.", file=sys.stderr)
    raise SystemExit(2)

client = OpenAI(api_key=api_key, base_url=base_url)

try:
    models = client.models.list()
    ids = [m.id for m in models.data]
    print("models_list_ok=1")
    print("available_models=" + ",".join(ids[:20]))
    if model not in ids:
        print(f"WARNING: CONVERSE_MODEL '{model}' was not in the first {min(20, len(ids))} listed models.")
except Exception as e:
    print(f"models_list_ok=0 error={type(e).__name__}: {e}")

completion = client.chat.completions.create(
    model=model,
    messages=[{"role": "user", "content": "Reply exactly: converse deepseek ok"}],
    temperature=0,
    max_tokens=20,
    stream=False,
    extra_body={"thinking": {"type": "disabled"}},
)
reply = (completion.choices[0].message.content or "").strip()
print("chat_ok=1")
print(f"reply={reply}")

# Exercise the exact first model request used by the target control workload.
# A tiny chat probe can pass even when the real structured prompt times out.
use_case = "real_estate"
persona_id = 1
_, _, _, user_task = load_persona_data_for_use_case(use_case, persona_id)
external_role = get_external_agent_role_for_use_case(use_case)
system_prompt = get_aggregated_prompts_for_planning_naive(use_case)
turn_prompt = start_plan_prompt.format(
    user_task,
    external_role,
    initial_plan_delimiter,
    initial_plan_delimiter,
)
started = time.monotonic()
completion = client.chat.completions.create(
    model=model,
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": turn_prompt},
    ],
    temperature=0,
    max_tokens=1000,
    stream=False,
    extra_body={"thinking": {"type": "disabled"}},
)
elapsed = time.monotonic() - started
content = completion.choices[0].message.content or ""
plan = extract_output(content, initial_plan_delimiter)
if not plan.strip():
    print("converse_initial_plan_ok=0", file=sys.stderr)
    print("ERROR: representative ConVerse response lacked the initial-plan delimiter", file=sys.stderr)
    raise SystemExit(1)
print("converse_initial_plan_ok=1")
print(f"converse_initial_plan_seconds={elapsed:.1f}")
print(f"converse_initial_plan_chars={len(content)}")
