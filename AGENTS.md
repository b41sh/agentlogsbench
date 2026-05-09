# Repository Guidelines

## Project Structure & Module Organization
This repository root is the active benchmark workspace. Keep reusable Python logic in `tooling/`, shared operational utilities and shared benchmark contracts in `common/`, and runnable engine lanes in `clickhouse/`, `doris/`, `elastic/`, `opensearch/`, and `postgres/`. Tests live under `tests/`. Runtime datasets in `common/generated/`, downloaded shards in `common/downloads/`, shared summaries in `common/results/`, and engine `results/` directories are disposable and should stay out of commits.

## Build, Test, and Development Commands
`python3 common/validate_edition.py` validates `common/config/edition.json`, query mappings, and adapter manifests.

`python3 -m unittest discover -s tests` runs the Python regression suite.

`python3 common/generate_small_data.py --output-dir common/generated/small` creates the bundled small observation dataset.

`python3 common/validate_generated_data.py --output-dir common/generated/small` validates generated rows and shape assumptions.

`bash benchmark.sh run-engine --engine clickhouse --result-name local-small` runs one manifest-driven engine lane.

`python3 common/validate_run_artifacts.py --results-dir clickhouse/results` verifies the result JSON contract after a run.

## Coding Style & Naming Conventions
Use 4-space indentation in Python. Keep `from __future__ import annotations` in new modules, prefer type hints, and use `pathlib.Path` for filesystem work. Reuse helpers from `tooling/` before introducing new abstractions or dependencies. Name tests `test_*.py`. Shell entrypoints should remain lowercase `*.sh`, start with `#!/usr/bin/env bash` and `set -euo pipefail`, and use uppercase variables such as `SCRIPT_DIR`. No repo-wide formatter is configured, so match nearby style and keep diffs small.

## Testing Guidelines
The test suite uses `unittest`. Add or update coverage for edition validation, data generation, scoring, summaries, and run-artifact validation when behavior changes. Put reusable fixtures in `tests/fixtures/`. Prefer the smallest convincing verification set first, then run lane-specific validation when engine outputs or artifact formats change.

## Commit & Pull Request Guidelines
Recent history uses short imperative commit subjects such as `refactor generator and correct SQL semantics`. Keep the first line focused on intent. When a body is needed, record the main constraint, rejected approaches, risk, and what you tested. Pull requests should state which benchmark surface changed, list verification commands, note the engines or dataset tiers exercised, and include updated summaries when benchmark outputs change.

## Artifacts & Configuration Tips
Do not commit `.omx/`, `generated/`, engine `results/`, local engine installs, or downloaded datasets unless the change explicitly requires tracked fixtures. Treat benchmark data, run outputs, and local runtimes as disposable workspace state.
