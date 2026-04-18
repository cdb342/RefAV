# Harbor Adapter for RefAV — Original-Side Parity

This is a fork of [CainanD/RefAV](https://github.com/CainanD/RefAV) with Harbor Scenario 2 parity support.

## What is this?

Harbor Scenario 2 requires running the **same agent on both sides** (Harbor and original) to demonstrate adapter equivalence. Since RefAV is LLM-based and doesn't natively support agent evaluation, this fork implements a Codex CLI runner that uses the **same Docker environment** as Harbor.

## Parity Scripts

| Script | Purpose |
|--------|---------|
| `run_original_parity.py` | Run Codex agent in Docker containers (original side) |
| `generate_parity_tasks.py` | Generate deterministic 50-task parity subset (seed=42) |

## Quick Start

### Prerequisites

- Docker installed and running
- Codex CLI config (`config.toml`) with API credentials
- RefAV dataset prepared (`datasets/refav/` with 1500 `val_*/` task directories)

### 1. Generate parity task list

```bash
python generate_parity_tasks.py \
    --dataset-dir /path/to/datasets/refav \
    --output parity_tasks.txt \
    --n 50 --seed 42
```

### 2. Run original-side parity

```bash
export CODEX_CONFIG_TOML=$(base64 < ~/.codex/config.toml)
export OPENAI_API_KEY="your-api-key"

python run_original_parity.py \
    --dataset-dir /path/to/datasets/refav \
    --task-list parity_tasks.txt \
    --output-dir results/original_run1 \
    --codex-model gpt-5.4-2026-03-05
```

### 3. Run Harbor-side parity (for comparison)

```bash
harbor run -p datasets/refav -a codex -m gpt-5.4-2026-03-05 \
    --force-build --timeout-multiplier 2.0 --agent-setup-timeout-multiplier 3.0 \
    --ak "reasoning_effort=low" -n 1 --n-tasks 50 -y
```

## Environment Parity

Both sides use:
- **Same Docker images** (built from `environment/Dockerfile` in each task)
- **Same resource limits** (`--cpus 2`, `--memory 16g`)
- **Same Codex CLI** (`@openai/codex@latest`)
- **Same model** (`gpt-5.4-2026-03-05`, `reasoning_effort=low`)
- **Same evaluation pipeline** (`run_code.py` → `compute_reward.py` → HOTA-Temporal)

## Parity Results

| Agent | Model | Metric | Trials | Original | Harbor |
|-------|-------|--------|--------|----------|--------|
| codex@0.116.0 | gpt-5.4-2026-03-05 | HOTA-Temporal | 3 | 0.486 ± 0.021 | 0.473 ± 0.025 |

Delta = 0.013, confidence intervals fully overlap.

## Links

- Harbor adapter PR: [cdb342/harbor/tree/refav-adapter](https://github.com/cdb342/harbor/tree/refav-adapter)
- Original RefAV: [CainanD/RefAV](https://github.com/CainanD/RefAV)
- Adapter maintainer: Dubing Chen (dobbin.chen@gmail.com)
