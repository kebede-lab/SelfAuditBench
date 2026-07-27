#!/usr/bin/env python3
"""Read-only ASB full-reproduction progress checker.

Run from the ASB repository root:
  python scripts/check_reproduction_progress.py
"""
import csv
import glob
import json
import os
import re
import subprocess
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PER_CONFIG = 400


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except Exception:
        return str(p)


def mtime(p: Path) -> str:
    if not p.exists():
        return "missing"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))


def age(p: Path) -> str:
    if not p.exists():
        return "missing"
    sec = max(0, int(time.time() - p.stat().st_mtime))
    if sec < 120:
        return f"{sec}s ago"
    if sec < 7200:
        return f"{sec//60}m ago"
    return f"{sec//3600}h{(sec%3600)//60:02d}m ago"


def count_csv_rows(p: Path) -> int:
    if not p.exists():
        return 0
    with p.open(newline="", errors="ignore") as f:
        return max(0, sum(1 for _ in f) - 1)


def tail_lines(p: Path, n: int = 20):
    if not p.exists():
        return []
    try:
        with p.open(errors="replace") as f:
            lines = f.readlines()
        return [x.rstrip("\n") for x in lines[-n:]]
    except Exception as e:
        return [f"<could not read tail: {e}>"]


def expected_tasks():
    tools_p = ROOT / "data" / "all_attack_tools.jsonl"
    tasks_p = ROOT / "data" / "agent_task.jsonl"
    if not tools_p.exists() or not tasks_p.exists():
        return EXPECTED_PER_CONFIG
    try:
        tools = [json.loads(l) for l in tools_p.read_text().splitlines() if l.strip()]
        tasks = [json.loads(l) for l in tasks_p.read_text().splitlines() if l.strip()]
        by_agent = Counter(t["Corresponding Agent"] for t in tools)
        return sum(by_agent[row["agent_name"]] * min(1, len(row.get("tasks", []))) for row in tasks)
    except Exception:
        return EXPECTED_PER_CONFIG


def newest(pattern: str):
    paths = [Path(p) for p in glob.glob(str(ROOT / pattern))]
    if not paths:
        return None
    return max(paths, key=lambda p: p.stat().st_mtime)


def print_processes():
    print("\nActive ASB/python processes:")
    try:
        out = subprocess.check_output(["ps", "-eo", "pid,etime,pcpu,pmem,stat,args"], text=True)
        hits = []
        for line in out.splitlines():
            if any(s in line for s in ["main_attacker.py", "agent_attack.py", "run_deepseek_full_reproduction"]):
                if "check_reproduction_progress.py" not in line:
                    hits.append(line)
        if hits:
            print("\n".join(hits))
        else:
            print("  none found; the run may have exited or be in a different account/session")
    except Exception as e:
        print(f"  could not inspect processes: {e}")


def main():
    os.chdir(ROOT)
    expected = expected_tasks()
    print(f"ASB root: {ROOT}")
    print(f"Expected rows per all/full config with task_num=1: {expected}")

    status = newest("logs/_run_status/deepseek_full_*.log")
    tmux_status = newest("logs/_run_status/tmux_deepseek_full_*.log")
    print("\nNewest status logs:")
    for label, p in [("inner", status), ("tmux tee", tmux_status)]:
        if p:
            print(f"  {label}: {rel(p)} size={p.stat().st_size} mtime={mtime(p)} age={age(p)}")
        else:
            print(f"  {label}: missing")

    if status:
        running = None
        finished = []
        for line in status.read_text(errors="replace").splitlines():
            m = re.search(r"==== running (.+?) at ", line)
            if m:
                running = m.group(1)
            m = re.search(r"==== finished (.+?) at ", line)
            if m:
                finished.append(m.group(1))
                if running == m.group(1):
                    running = None
        print("\nStatus-log interpretation:")
        print(f"  finished configs: {len(finished)} -> {finished}")
        print(f"  current/unfinished config: {running or 'none according to status log'}")

    print_processes()

    print("\nDeepSeek official full result files:")
    files = sorted(Path("logs").glob("**/*_deepseek_full.csv"))
    if not files:
        print("  no CSV files found")
    for csv_p in files:
        log_p = csv_p.with_suffix(".log")
        rows = count_csv_rows(csv_p)
        pct = (100.0 * rows / expected) if expected else 0.0
        print(f"  {rel(csv_p)} rows={rows}/{expected} ({pct:.1f}%) csv_age={age(csv_p)} log_age={age(log_p)}")

    current_log = newest("logs/memory_attack/deepseek-v4-flash/new_memory/*_deepseek_full.log")
    current_csv = newest("logs/memory_attack/deepseek-v4-flash/new_memory/*_deepseek_full.csv")
    print("\nNewest MP files:")
    for label, p in [("MP log", current_log), ("MP csv", current_csv)]:
        if p:
            print(f"  {label}: {rel(p)} size={p.stat().st_size} mtime={mtime(p)} age={age(p)}")
        else:
            print(f"  {label}: missing")
    if current_log:
        print("\nTail of newest MP log:")
        for line in tail_lines(current_log, 30):
            print(line)

    print("\nFailure hints:")
    search_paths = [p for p in [status, tmux_status, current_log] if p]
    for p in search_paths:
        text = p.read_text(errors="replace")[-200000:]
        hits = [s for s in ["Traceback", "Error:", "RateLimit", "timeout", "KeyboardInterrupt", "Command failed", "APIConnectionError"] if s in text]
        if hits:
            print(f"  {rel(p)} contains: {', '.join(hits)}")


if __name__ == "__main__":
    main()
