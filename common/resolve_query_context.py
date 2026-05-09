#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Iterator, TextIO

REQUIRED_CONTEXT_KEYS = (
    "tenant",
    "app",
    "trace_id",
    "release_ring",
    "customer_tier",
    "traffic_cluster",
    "request_key",
    "workflow_variant",
    "start_date",
    "end_date",
)


ROW_CONTEXT_KEYS = REQUIRED_CONTEXT_KEYS[:-2]


def row_context_is_complete(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    return all(str(payload.get(key) or "").strip() for key in ROW_CONTEXT_KEYS)


def context_is_complete(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    return all(str(payload.get(key) or "").strip() for key in REQUIRED_CONTEXT_KEYS)


def iter_dataset_files(data_dir: Path, size: str) -> list[Path]:
    file_count = {"1m": 1, "10m": 10, "100m": 100}[size]
    files = [data_dir / f"agent_observations_{index:04d}.ndjson.gz" for index in range(1, file_count + 1)]
    missing = [str(path) for path in files if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing dataset files: {missing}")
    return files


def open_text(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def iter_rows(files: Iterable[Path]) -> Iterator[dict[str, object]]:
    for path in files:
        with open_text(path) as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                yield json.loads(line)


def _row_context(row: dict[str, object]) -> dict[str, str]:
    payload = row.get("payload")
    attr = payload.get("attr", {}) if isinstance(payload, dict) else {}

    def attr_text(key: str) -> str:
        value = attr.get(key) if isinstance(attr, dict) else ""
        return str(value or "")

    return {
        "tenant": str(row.get("tenant") or ""),
        "app": str(row.get("app") or ""),
        "trace_id": str(row.get("trace_id") or ""),
        "release_ring": attr_text("release_ring"),
        "customer_tier": attr_text("customer_tier"),
        "traffic_cluster": attr_text("traffic_cluster"),
        "request_key": attr_text("request_key"),
        "workflow_variant": attr_text("workflow_variant"),
    }


def resolve_context(files: Iterable[Path]) -> dict[str, str]:
    phrase_pair_counts: dict[tuple[str, str], int] = defaultdict(int)
    first_complete_pair: tuple[str, str] | None = None
    pair_first_complete_context: dict[tuple[str, str], dict[str, str]] = {}
    pair_duplicate_complete_context: dict[tuple[str, str], dict[str, str]] = {}
    pair_seen_trace_ids: dict[tuple[str, str], set[str]] = defaultdict(set)
    min_date: str | None = None
    max_date: str | None = None

    for row in iter_rows(files):
        tenant = str(row.get("tenant") or "")
        app = str(row.get("app") or "")
        trace_id = str(row.get("trace_id") or "")
        biz_date = str(row.get("biz_date") or "")
        row_context: dict[str, str] | None = None

        if tenant and app:
            pair = (tenant, app)
            row_context = _row_context(row)
            is_duplicate_trace = False
            if trace_id:
                is_duplicate_trace = trace_id in pair_seen_trace_ids[pair]
                pair_seen_trace_ids[pair].add(trace_id)
            if row_context_is_complete(row_context):
                pair_first_complete_context.setdefault(pair, row_context)
                if first_complete_pair is None:
                    first_complete_pair = pair
                if is_duplicate_trace and pair not in pair_duplicate_complete_context:
                    pair_duplicate_complete_context[pair] = row_context

        if biz_date:
            if min_date is None or biz_date < min_date:
                min_date = biz_date
            if max_date is None or biz_date > max_date:
                max_date = biz_date

        if (
            tenant
            and app
            and str(row.get("type") or "") == "TOOL"
            and str(row.get("status") or "") == "error"
        ):
            haystack = f"{row.get('input') or ''} {row.get('output') or ''}".lower()
            if "unable to open" in haystack:
                phrase_pair_counts[(tenant, app)] += 1

    if phrase_pair_counts:
        selected_pair = sorted(
            phrase_pair_counts.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        )[0][0]
    elif first_complete_pair is not None:
        selected_pair = first_complete_pair
    else:
        raise ValueError("Could not resolve a complete query context from dataset files")

    context = pair_duplicate_complete_context.get(selected_pair) or pair_first_complete_context.get(selected_pair)
    if context is None:
        tenant, app = selected_pair
        raise ValueError(f"Could not resolve a complete query context for tenant={tenant} app={app}")
    if min_date is None or max_date is None:
        raise ValueError("Could not resolve biz_date range from dataset files")

    context["start_date"] = min_date
    context["end_date"] = max_date
    return context


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve a shared benchmark query context from downloaded dataset files.")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--size", choices=("1m", "10m", "100m"), required=True)
    parser.add_argument("--output-file", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.output_file and args.output_file.exists() and not args.force:
        payload = json.loads(args.output_file.read_text(encoding="utf-8"))
        if context_is_complete(payload):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

    payload = resolve_context(iter_dataset_files(args.data_dir, args.size))
    if args.output_file:
        args.output_file.parent.mkdir(parents=True, exist_ok=True)
        args.output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
