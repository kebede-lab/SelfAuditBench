"""OpenAI-compatible API online auditing inference on AFTraj-2K.

Same protocol as ``infer_local.py`` but the auditor is queried over an
OpenAI-compatible chat completions endpoint. The local reproduction defaults to
the CSTCloud OpenAI-compatible gateway. Set ``OPENAI_API_KEY`` and override
``AGENTFORESIGHT_BASE_URL`` or ``--base-url`` only when needed.

Example::

    export OPENAI_API_KEY=...
    python -m inference.infer_api \\
        --data-dir    ./data \\
        --output-dir  ./outputs/cstcloud-deepseek-v4-flash \\
        --paper-test-split \\
        --macro-domain \\
        --resume
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from openai import OpenAI
from tqdm import tqdm

from inference.data import TrajectoryRecord, load_aftraj
from inference.metrics import aggregate_by_domain, format_report, per_sample_metrics
from inference.prompts import AuditVerdict, build_messages, parse_response

DEFAULT_BASE_URL = "https://uni-api.cstcloud.cn/v1"
DEFAULT_MODEL = "deepseek-v4-flash"


def call_api(client: OpenAI, model: str, messages: list[dict],
             max_tokens: int, temperature: float) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""

def audit_full(client, model: str, rec: TrajectoryRecord,
               max_tokens: int, temperature: float) -> tuple[AuditVerdict, float, int]:
    msgs = build_messages(rec.turns, tools=rec.tools, current_step=None)
    t0 = time.time()
    raw = call_api(client, model, msgs, max_tokens, temperature)
    return parse_response(raw), time.time() - t0, 1

def audit_incremental(client, model: str, rec: TrajectoryRecord,
                      max_tokens: int, temperature: float) -> tuple[AuditVerdict, float, int, int]:
    total_time = 0.0
    n_calls = 0
    last: AuditVerdict | None = None
    detection_step = rec.num_turns - 1
    for k in range(rec.num_turns):
        msgs = build_messages(rec.turns, tools=rec.tools, current_step=k)
        t0 = time.time()
        raw = call_api(client, model, msgs, max_tokens, temperature)
        total_time += time.time() - t0
        n_calls += 1
        last = parse_response(raw)
        if last.valid and last.pred_step >= 0:
            detection_step = k
            return last, total_time, n_calls, detection_step
    return last or AuditVerdict(-1, "", "", False, ""), total_time, n_calls, detection_step


def load_completed_rows(path: Path) -> list[dict]:
    """Load successful partial output so an interrupted paid run can resume."""

    if not path.exists():
        return []
    rows: list[dict] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for line_number, line in enumerate(lines, start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            if line_number == len(lines):
                print(f"WARNING: ignoring truncated final JSONL line at {path}:{line_number}")
                break
            raise ValueError(f"invalid JSONL at {path}:{line_number}") from exc
        if row.get("_record_type") != "config":
            rows.append(row)
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model",       default=None,         help=f"OpenAI-compatible model name (default: ${'{'}AGENTFORESIGHT_MODEL{'}'} or {DEFAULT_MODEL}).")
    p.add_argument("--data-dir",    default="./data")
    p.add_argument("--output-dir",  default="./outputs_api")
    p.add_argument("--max-tokens",  type=int,   default=2048)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--max-trajs",   type=int,   default=None, help="Optional cap (smoke test).")
    p.add_argument("--domains",     type=str,   default=None, help="Comma-separated domain whitelist.")
    p.add_argument("--splits",      type=str,   default="safe,unsafe", help="Comma-separated split whitelist: safe,unsafe.")
    p.add_argument("--base-url",    default=None,             help=f"Override OpenAI base URL (default: ${'{'}AGENTFORESIGHT_BASE_URL{'}'} or {DEFAULT_BASE_URL}).")
    p.add_argument("--timeout-seconds", type=float, default=float(os.environ.get("AGENTFORESIGHT_TIMEOUT_SECONDS", "120")))
    p.add_argument("--max-retries", type=int, default=int(os.environ.get("AGENTFORESIGHT_MAX_RETRIES", "3")))
    p.add_argument("--resume", action="store_true", help="Append to per_sample.jsonl and skip completed trajectory IDs.")
    p.add_argument("--paper-test-split", action="store_true",
                   help="Restrict to the held-out test split used in the paper's main table.")
    p.add_argument("--macro-domain", action="store_true",
                   help="Aggregate metrics by the paper's 3-way macro buckets (Math/Coding/Agentic).")
    args = p.parse_args()

    if "OPENAI_API_KEY" not in os.environ:
        raise SystemExit("OPENAI_API_KEY is not set.")

    model = args.model or os.environ.get("AGENTFORESIGHT_MODEL") or os.environ.get("MODEL_NAME") or DEFAULT_MODEL
    base_url = (
        args.base_url
        or os.environ.get("AGENTFORESIGHT_BASE_URL")
        or os.environ.get("BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("OPENAI_API_BASE")
        or DEFAULT_BASE_URL
    )
    client = OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=base_url,
        timeout=args.timeout_seconds,
        max_retries=args.max_retries,
    )

    domains = [d.strip() for d in args.domains.split(",")] if args.domains else None
    splits = tuple(split.strip() for split in args.splits.split(",") if split.strip())
    records = load_aftraj(args.data_dir, domains=domains, limit=args.max_trajs,
                          splits=splits, paper_test_split=args.paper_test_split)
    print(f"Loaded {len(records)} trajectories from {args.data_dir}")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "per_sample.jsonl"
    json_path  = out_dir / "results.json"

    per_sample = load_completed_rows(jsonl_path) if args.resume else []
    completed = {str(row["conv_id"]) for row in per_sample}
    pending = [rec for rec in records if rec.conv_id not in completed]
    if completed:
        print(f"Resuming with {len(completed)} completed trajectories; {len(pending)} remain")

    mode = "a" if args.resume and jsonl_path.exists() else "w"
    with open(jsonl_path, mode, encoding="utf-8") as f:
        config = {
            "model":       model,
            "data_dir":    str(Path(args.data_dir).resolve()),
            "max_tokens":  args.max_tokens,
            "temperature": args.temperature,
            "domains":     domains,
            "splits":      splits,
            "base_url":    base_url,
            "timeout_seconds": args.timeout_seconds,
            "max_retries": args.max_retries,
            "paper_test_split": args.paper_test_split,
            "resume":      args.resume,
        }
        f.write(json.dumps({"_record_type": "config", **config}, ensure_ascii=False) + "\n")
        f.flush()

        for rec in tqdm(pending, desc="audit-api"):
            if rec.label == "safe":
                verdict, gen_s, n_calls = audit_full(
                    client, model, rec, args.max_tokens, args.temperature
                )
                detection_step = -1
            else:
                verdict, gen_s, n_calls, detection_step = audit_incremental(
                    client, model, rec, args.max_tokens, args.temperature
                )

            row = {
                "conv_id":        rec.conv_id,
                "domain":         rec.domain,
                "label":          rec.label,
                "gt_step":        rec.mistake_step,
                "pred_step":      verdict.pred_step,
                "pred_agent":     verdict.pred_agent,
                "pred_reason":    verdict.pred_reason,
                "format_valid":   verdict.valid,
                "detection_step": detection_step,
                "num_turns":      rec.num_turns,
                "num_calls":      n_calls,
                "gen_time_s":     round(gen_s, 2),
                "raw_response":   verdict.raw_response[:3000],
                **per_sample_metrics(verdict.pred_step, rec.mistake_step),
            }
            per_sample.append(row)
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            f.flush()

    by_domain = aggregate_by_domain(per_sample, macro=args.macro_domain)
    print("\n" + format_report(by_domain))

    json_path.write_text(
        json.dumps({"by_domain": by_domain, "per_sample": per_sample}, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\nResults written to {json_path}")

if __name__ == "__main__":
    main()
