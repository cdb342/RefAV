#!/usr/bin/env python3
"""Generate the deterministic 50-task parity subset (seed=42, non-empty GT)."""

import argparse
import json
import random
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("parity_tasks.txt"))
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    non_empty = []
    for task_dir in sorted(args.dataset_dir.iterdir()):
        if not task_dir.name.startswith("val_"):
            continue
        gt = task_dir / "tests" / "gt_set.json"
        if gt.exists():
            data = json.loads(gt.read_text())
            if isinstance(data, list) and len(data) > 0:
                non_empty.append(task_dir.name)

    print(f"Tasks with non-empty GT: {len(non_empty)}")
    random.seed(args.seed)
    parity = sorted(random.sample(non_empty, min(args.n, len(non_empty))))
    args.output.write_text("\n".join(parity) + "\n")
    print(f"Parity subset ({len(parity)} tasks) written to {args.output}")


if __name__ == "__main__":
    main()
