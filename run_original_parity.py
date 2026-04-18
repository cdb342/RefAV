#!/usr/bin/env python3
"""
Original-side parity runner for RefAV × Harbor.

Runs the same Codex CLI agent inside the same Docker environment as Harbor,
ensuring environment parity. Each task is:
  1. Built from environment/Dockerfile (same image as Harbor)
  2. Codex CLI installed, configured, and run with instruction.md
  3. test.sh evaluates the solution (same verifier as Harbor)

Resource limits (--cpus 2, --memory 16g) match Harbor's task.toml.

Usage:
  export CODEX_CONFIG_TOML=$(base64 < ~/.codex/config.toml)
  export OPENAI_API_KEY="your-key"
  python run_original_parity.py \
      --dataset-dir /path/to/datasets/refav \
      --task-list /path/to/parity_tasks.txt \
      --output-dir /path/to/output \
      --codex-model gpt-5.4-2026-03-05
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ENTRYPOINT_TEMPLATE = r"""#!/bin/bash
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq > /dev/null 2>&1
apt-get install -y -qq curl > /dev/null 2>&1
curl -fsSL https://deb.nodesource.com/setup_22.x 2>/dev/null | bash - > /dev/null 2>&1
apt-get install -y -qq nodejs > /dev/null 2>&1
npm install -g @openai/codex@latest > /dev/null 2>&1

CODEX_HOME=/root/.codex
mkdir -p "$CODEX_HOME"
echo "$CODEX_CONFIG_B64" | base64 -d > "$CODEX_HOME/config.toml"
mkdir -p /tmp/codex-secrets
printf '{"OPENAI_API_KEY":"%s"}' "$OPENAI_API_KEY" > /tmp/codex-secrets/auth.json
ln -sf /tmp/codex-secrets/auth.json "$CODEX_HOME/auth.json"

INSTRUCTION=$(cat /mnt/instruction.md)
cd /data
codex exec \
    --dangerously-bypass-approvals-and-sandbox \
    --skip-git-repo-check \
    --model "$CODEX_MODEL" \
    --json \
    -c model_reasoning_effort=low \
    -- "$INSTRUCTION" \
    </dev/null > /tmp/codex_output.txt 2>&1 || true

mkdir -p /logs/verifier
bash /tests/test.sh > /tmp/test_output.txt 2>&1 || true
cat /logs/verifier/reward.txt 2>/dev/null || echo "0.0"
"""


def run_task(task_id, dataset_dir, output_dir, codex_config_b64, codex_model, task_num):
    task_dir = dataset_dir / task_id
    trial_dir = output_dir / task_id
    trial_dir.mkdir(parents=True, exist_ok=True)

    env_dir = task_dir / "environment"
    image_name = f"refav-original-{task_id.replace('_', '-')}"

    print(f"\n[{task_num}] {task_id}")

    t0 = time.time()
    r = subprocess.run(
        ["docker", "build", "-q", "-t", image_name, str(env_dir)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if r.returncode != 0:
        print(f"  FAIL: Docker build error")
        return {"task": task_id, "reward": None, "error": "docker_build"}
    print(f"  Image built in {time.time() - t0:.0f}s")

    inst_file = trial_dir / "instruction.md"
    inst_file.write_text((task_dir / "instruction.md").read_text())
    ent_file = trial_dir / "entrypoint.sh"
    ent_file.write_text(ENTRYPOINT_TEMPLATE)

    print(f"  Running Codex in container...")
    t0 = time.time()
    try:
        r = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-e",
                f"CODEX_CONFIG_B64={codex_config_b64}",
                "-e",
                f"OPENAI_API_KEY={os.environ.get('OPENAI_API_KEY', 'placeholder')}",
                "-e",
                f"CODEX_MODEL={codex_model}",
                "-v",
                f"{task_dir / 'tests'}:/tests:ro",
                "-v",
                f"{inst_file}:/mnt/instruction.md:ro",
                "-v",
                f"{ent_file}:/mnt/entrypoint.sh:ro",
                "--cpus",
                "2",
                "--memory",
                "16g",
                image_name,
                "bash",
                "/mnt/entrypoint.sh",
            ],
            capture_output=True,
            text=True,
            timeout=1200,
        )
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT (1200s)")
        return {"task": task_id, "reward": 0.0, "duration": 1200, "error": "timeout"}

    duration = time.time() - t0
    stdout_lines = r.stdout.strip().split("\n")
    reward_str = stdout_lines[-1].strip() if stdout_lines else "0.0"
    try:
        reward = float(reward_str)
    except ValueError:
        reward = 0.0

    print(f"  Reward: {reward:.4f} ({duration:.0f}s)")
    result = {"task": task_id, "reward": reward, "duration": round(duration, 1)}
    (trial_dir / "result.json").write_text(json.dumps(result, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Original-side parity runner for RefAV"
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        required=True,
        help="Path to datasets/refav/ containing val_*/ task dirs",
    )
    parser.add_argument(
        "--task-list",
        type=Path,
        required=True,
        help="File with one task ID per line (e.g., parity_tasks.txt)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory to write per-task results",
    )
    parser.add_argument(
        "--codex-model", default="gpt-5.4-2026-03-05", help="Model ID for Codex CLI"
    )
    args = parser.parse_args()

    codex_config_b64 = os.environ.get("CODEX_CONFIG_TOML", "")
    if not codex_config_b64:
        print(
            "ERROR: Set CODEX_CONFIG_TOML env var (base64-encoded config.toml)",
            file=sys.stderr,
        )
        sys.exit(1)

    tasks = [
        t.strip() for t in args.task_list.read_text().strip().split("\n") if t.strip()
    ]
    print(f"Running original parity: {len(tasks)} tasks, model={args.codex_model}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for i, task_id in enumerate(tasks, 1):
        result = run_task(
            task_id,
            args.dataset_dir,
            args.output_dir,
            codex_config_b64,
            args.codex_model,
            i,
        )
        results.append(result)

    valid = [r for r in results if r.get("reward") is not None]
    rewards = [r["reward"] for r in valid]
    mean = sum(rewards) / len(rewards) if rewards else 0

    print(f"\n{'=' * 50}")
    print(f"Total: {len(results)}, Valid: {len(valid)}")
    print(f"Mean reward: {mean:.4f}")
    print(f"reward=1.0: {sum(1 for r in rewards if r == 1.0)}")
    print(f"reward>0: {sum(1 for r in rewards if r > 0)}")
    print(f"reward=0: {sum(1 for r in rewards if r == 0)}")

    summary = {
        "total": len(results),
        "valid": len(valid),
        "mean_reward": round(mean, 4),
        "results": results,
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nResults saved to {args.output_dir}/summary.json")


if __name__ == "__main__":
    main()
