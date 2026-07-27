#!/usr/bin/env python3
"""Official DeepSeek chat smoke test for ASB without printing secrets."""
import os
import sys
from openai import OpenAI

base_url = os.getenv("BASE_URL") or os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE") or "https://api.deepseek.com/v1"
model = os.getenv("ASB_MODEL") or "deepseek-v4-flash"
key = os.getenv("OPENAI_API_KEY")

if not key:
    print("ERROR: OPENAI_API_KEY is not set. Export your official DeepSeek token first.", file=sys.stderr)
    sys.exit(2)

client = OpenAI(api_key=key, base_url=base_url)
print(f"base_url={base_url}")
print(f"model={model}")

try:
    try:
        models = client.models.list()
        ids = [m.id for m in models.data]
        print("models_list_ok=1")
        if ids:
            print("available_models=" + ",".join(ids[:50]))
            if model not in ids:
                print(f"WARNING: ASB_MODEL '{model}' was not in the first {min(50, len(ids))} listed models.")
    except Exception as e:
        print(f"models_list_ok=0 ({type(e).__name__}: {str(e)[:180]})")

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role":"user","content":"Reply exactly: asb deepseek ok"}],
        max_tokens=20,
        temperature=0,
    )
    print("chat_ok=1")
    print("reply=" + (resp.choices[0].message.content or "").strip())
except Exception as e:
    print(f"chat_ok=0 ({type(e).__name__}: {str(e)[:500]})", file=sys.stderr)
    sys.exit(1)
