#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def resolve_input_paths(input_files: list[str], input_glob: str | None) -> list[Path]:
    if input_files:
        return [Path(item).resolve() for item in input_files]
    if input_glob:
        return [Path(item).resolve() for item in sorted(glob.glob(input_glob))]
    raise ValueError("Provide --input-files or --input-glob")


def build_dataset(
    input_paths: list[Path],
    output_dir: Path,
    dataset_version: str,
    target_rows: int,
    input_glob: str | None,
) -> dict[str, Any]:
    if not input_paths:
        raise ValueError("No input files resolved")

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    summary_path = output_dir / "summary.json"
    source_files = [str(path) for path in input_paths]

    manifest: dict[str, Any] = {
        "edition": dataset_version,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_files": source_files,
        "observation_rows": target_rows if target_rows > 0 else None,
    }
    if input_glob:
        manifest["input_glob"] = input_glob

    summary = {
        "dataset_version": dataset_version,
        "source_files": source_files,
        "source_file_count": len(source_files),
        "observation_rows": target_rows if target_rows > 0 else None,
    }

    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "output_dir": str(output_dir),
        "manifest_path": str(manifest_path),
        "summary_path": str(summary_path),
        "source_file_count": len(source_files),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Write lightweight metadata for an external benchmark dataset.")
    parser.add_argument("--input-files", nargs="*", default=[], help="Ordered input files, supports .ndjson and .ndjson.gz")
    parser.add_argument("--input-glob", default=None, help="Glob for ordered input files when --input-files is omitted")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output-file-name", default="agent_observations_external.ndjson", help="Ignored; kept for CLI compatibility")
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--target-rows", type=int, default=0, help="Optional metadata-only row count; 0 means unknown")
    args = parser.parse_args()

    result = build_dataset(
        resolve_input_paths(args.input_files, args.input_glob),
        args.output_dir,
        args.dataset_version,
        args.target_rows,
        args.input_glob,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
