#!/usr/bin/env python3
"""Download the official AFTraj-2K parquet artifacts into the local workspace."""

from __future__ import annotations

import argparse
from pathlib import Path

from huggingface_hub import snapshot_download

REQUIRED_ARTIFACTS = (
    "aftraj_safe.parquet",
    "aftraj_unsafe.parquet",
    "splits_test.json",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="./data")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id="ZBox008003/AFTraj",
        repo_type="dataset",
        local_dir=output_dir,
        allow_patterns=list(REQUIRED_ARTIFACTS),
    )

    missing = [name for name in REQUIRED_ARTIFACTS if not (output_dir / name).exists()]
    if missing:
        raise SystemExit(f"Missing downloaded artifacts: {', '.join(missing)}")
    for name in REQUIRED_ARTIFACTS:
        print(f"ready={output_dir / name}")


if __name__ == "__main__":
    main()
