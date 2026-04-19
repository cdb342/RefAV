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

## Evaluation Metrics

The original RefAV benchmark reports 4 metrics (from `av2.evaluation.scenario_mining.eval.evaluate()`):

| Metric | Description | Used as Harbor reward? |
|--------|-------------|----------------------|
| **HOTA-Temporal** | HOTA on temporally-localized referred tracks — the primary competition metric | Yes |
| HOTA-Track | HOTA on the full length of any referred track | No |
| Timestamp Balanced Accuracy | Per-timestamp: does this frame contain the described scenario? | No |
| Scenario Balanced Accuracy | Per-log: does this log contain the described scenario? | No |

HOTA-Temporal is used as the single reward value, consistent with the [EvalAI competition leaderboard](https://eval.ai/web/challenges/challenge-page/2662/overview). All 4 metrics are computed and printed to stdout during evaluation.

## Differences Between Adapter and Original RefAV Pipeline

### Data

| Aspect | Original RefAV | Harbor Adapter |
|--------|---------------|----------------|
| Raw AV2 sensor data (~1TB) | Required for tracker models and drivable area filtering | Not required — pre-computed tracking data is shipped per task |
| Tracking data source | `scenario_mining_val_annotations.feather` (1.08GB, HuggingFace) — contains all 3D bboxes + tracks + per-prompt `mining_category` labels | Per-task `sm_annotations.feather` (~5MB) — same tracking+bbox data but **label columns stripped** (mining_category, prompt, log_id removed) |
| Ground truth | `mining_category` column in annotation feather → converted to evaluation pkl via `create_gt_mining_pkls_parallel()` | `gt_set.json` — simplified `[(track_uuid, timestamp_ns), ...]` list of REFERRED_OBJECT entries, isolated in `tests/` directory |
| Tracker model outputs (Google Drive, 4.3GB) | For test split competition submissions only | Not applicable — val split uses official annotations |

### Code Generation

| Aspect | Original RefAV | Harbor Adapter |
|--------|---------------|----------------|
| Prompt | `build_context()` — single user message with atomic_functions.txt + categories.txt + examples.txt | `instruction.md` — same content + additional CRITICAL CONSTRAINTS section |
| LLM invocation | Direct API call via `predict_scenario_openai/google/anthropic()` | Codex CLI agent reads instruction.md → writes /data/solution.py |
| CRITICAL CONSTRAINTS | Not present | Added to prevent Codex from exploring raw log data in `/data/log_dir/` and to encourage short atomic-function compositions |

### Evaluation

| Aspect | Original RefAV | Harbor Adapter |
|--------|---------------|----------------|
| Evaluation function | `av2.evaluation.scenario_mining.eval.evaluate()` | Same |
| `max_range_m` | 50 | 50 |
| `filter_max_dist()` | Applied | Applied |
| `filter_drivable_area()` | Applied (requires AV2 sensor dataset path) | **Skipped** (`dataset_dir=None`) — AV2 sensor data not shipped |
| Evaluation timestamps | `log_timestamps[::5]` (10Hz → 2Hz) | Same |
| Reward | HOTA-Temporal averaged across all prompts | HOTA-Temporal per-task (each task = one prompt) |

### Known Differences

1. **Drivable area ROI filtering disabled**: `filter_drivable_area()` requires the full AV2 sensor dataset (~1TB) for HD map polygon data. Since we don't ship it, `dataset_dir=None` skips this filter. Impact: minimal — GT objects are already constrained to "within 5m of a mapped road" by annotation rules, and atomic functions return objects from `sm_annotations.feather` which are within road area.

2. **GT format**: Original uses pkl from `create_gt_mining_pkls_parallel()`. Adapter uses `gt_set.json` → `create_mining_pkl()`. Both produce the same evaluation pkl structure.

3. **Instruction augmentation**: `instruction.md` adds CRITICAL CONSTRAINTS not in original `build_context()`. Necessary because Codex/claude-code can execute arbitrary commands unlike the original single-LLM-call pipeline.

4. **Per-task evaluation**: Original evaluates all prompts together. Adapter evaluates each (log, prompt) independently. HOTA-Temporal is equivalent per-task.

## Links

- Harbor adapter: [cdb342/harbor/tree/refav-adapter](https://github.com/cdb342/harbor/tree/refav-adapter)
- Original RefAV: [CainanD/RefAV](https://github.com/CainanD/RefAV)
- Adapter maintainer: Dubing Chen (dobbin.chen@gmail.com)
