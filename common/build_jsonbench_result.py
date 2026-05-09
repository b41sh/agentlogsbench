#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

TIME_PATTERN = re.compile(r"Response time:\s*([0-9]+(?:\.[0-9]+)?)\s*s")


def read_number(path: Path | None, value_type: type[Any]) -> Any | None:
    if path is None or not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    return value_type(text)


def parse_runtime_matrix(runtime_path: Path, tries: int) -> list[list[float]]:
    timings = [float(match.group(1)) for match in TIME_PATTERN.finditer(runtime_path.read_text(encoding="utf-8"))]
    if not timings:
        raise ValueError(f"No runtime rows found in {runtime_path}")
    if len(timings) % tries != 0:
        raise ValueError(f"Runtime rows in {runtime_path} are not divisible by tries={tries}")
    return [timings[index:index + tries] for index in range(0, len(timings), tries)]


def relative_artifact_path(output_file: Path, artifact_path: Path) -> str:
    try:
        return str(artifact_path.relative_to(output_file.parent))
    except ValueError:
        return artifact_path.name


def dump_with_linewise_result(payload: dict[str, Any]) -> str:
    result = payload.get("result")
    if not isinstance(result, list):
        return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    placeholder = "__AIBENCH_RESULT_PLACEHOLDER__"
    payload_for_dump = dict(payload)
    payload_for_dump["result"] = placeholder
    rendered = json.dumps(payload_for_dump, indent=2, ensure_ascii=False)

    if not result:
        rendered = rendered.replace(f'"{placeholder}"', "[]", 1)
        return rendered + "\n"

    linewise_result = "[\n" + "\n".join(
        f"    {json.dumps(item, ensure_ascii=False, separators=(', ', ': '))}{',' if index < len(result) - 1 else ''}"
        for index, item in enumerate(result)
    ) + "\n  ]"
    rendered = rendered.replace(f'"{placeholder}"', linewise_result, 1)
    return rendered + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a JSONBench-style result document from temporary metric files.")
    parser.add_argument("--system", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--os", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--machine", required=True)
    parser.add_argument("--dataset-size", type=int, required=True)
    parser.add_argument("--retains-structure", default="yes")
    parser.add_argument("--tries", type=int, default=3)
    parser.add_argument("--runtime-file", type=Path, required=True)
    parser.add_argument("--count-file", type=Path, required=True)
    parser.add_argument("--total-size-file", type=Path, required=True)
    parser.add_argument("--data-size-file", type=Path)
    parser.add_argument("--index-size-file", type=Path)
    parser.add_argument("--load-time-file", type=Path)
    parser.add_argument("--tags", default="")
    parser.add_argument("--output-file", type=Path, required=True)
    parser.add_argument("--query-results-file", type=Path)
    args = parser.parse_args()

    result_matrix = parse_runtime_matrix(args.runtime_file, args.tries)
    num_loaded_documents = int(read_number(args.count_file, int) or 0)
    total_size = int(read_number(args.total_size_file, int) or 0)

    payload: dict[str, Any] = {
        "system": args.system,
        "version": args.version,
        "os": args.os,
        "date": args.date,
        "machine": args.machine,
        "retains_structure": args.retains_structure,
        "tags": [tag for tag in (item.strip() for item in args.tags.split(",")) if tag],
        "dataset_size": args.dataset_size,
        "num_loaded_documents": num_loaded_documents,
        "total_size": total_size,
        "result": result_matrix,
    }
    artifact_manifest: dict[str, Any] = {
        "embedded_sidecars": [
            {
                "name": args.count_file.name,
                "field": "num_loaded_documents",
                "value": num_loaded_documents,
            },
            {
                "name": args.total_size_file.name,
                "field": "total_size",
                "value": total_size,
            },
            {
                "name": args.runtime_file.name,
                "field": "result",
                "rows": len(result_matrix),
                "tries": args.tries,
            },
        ]
    }

    data_size = read_number(args.data_size_file, int)
    index_size = read_number(args.index_size_file, int)
    load_time = read_number(args.load_time_file, float)
    if data_size is not None:
        payload["data_size"] = int(data_size)
        artifact_manifest["embedded_sidecars"].append({
            "name": args.data_size_file.name,
            "field": "data_size",
            "value": int(data_size),
        })
    if index_size is not None:
        payload["index_size"] = int(index_size)
        artifact_manifest["embedded_sidecars"].append({
            "name": args.index_size_file.name,
            "field": "index_size",
            "value": int(index_size),
        })
    if load_time is not None:
        payload["load_time"] = round(float(load_time), 3)
        artifact_manifest["embedded_sidecars"].append({
            "name": args.load_time_file.name,
            "field": "load_time",
            "value": payload["load_time"],
        })
    if args.query_results_file is not None:
        artifact_manifest["query_results"] = {
            "path": relative_artifact_path(args.output_file, args.query_results_file),
        }
    payload["artifact_manifest"] = artifact_manifest

    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    args.output_file.write_text(dump_with_linewise_result(payload), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
