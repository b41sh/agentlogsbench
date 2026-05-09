from __future__ import annotations

import gzip
import json
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List

from agentlogsbench.tooling.validate_generated import REQUIRED_OBSERVATION_FIELDS


def _open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def _iter_ndjson(paths: Iterable[Path]) -> Iterable[Dict[str, Any]]:
    for path in paths:
        with _open_text(path) as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield json.loads(line)


def validate_large_generated_dataset(output_dir: Path) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []

    manifest_path = output_dir / "manifest.json"
    summary_path = output_dir / "summary.json"
    labels_path = output_dir / "accuracy_labels.json"
    for path in (manifest_path, summary_path, labels_path):
        if not path.exists():
            errors.append(f"missing file: {path}")
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    labels = json.loads(labels_path.read_text(encoding="utf-8"))

    shard_specs = manifest.get("observation_files", [])
    if not shard_specs:
        errors.append("manifest missing observation_files")
        return {"ok": False, "errors": errors, "warnings": warnings}

    shard_paths: List[Path] = []
    for item in shard_specs:
        relative = item["path"] if isinstance(item, dict) else str(item)
        shard_path = output_dir / relative
        if not shard_path.exists():
            errors.append(f"missing shard: {shard_path}")
        else:
            shard_paths.append(shard_path)
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}

    observation_rows = 0
    generation_rows = 0
    replay_observation_found = False
    replay_trace_found = False
    row_hint = int(summary.get("observation_rows", 0) or 0)
    use_external_sort = row_hint > 1_000_000 and shutil.which("sort") is not None
    observation_ids = set()
    trace_ids = set()
    duplicate_observation_id = None

    with tempfile.TemporaryDirectory(prefix="ajb-large-validate-") as temp_dir:
        obs_path = Path(temp_dir) / "observation_ids.txt"
        trace_path = Path(temp_dir) / "trace_ids.txt"
        db_path = Path(temp_dir) / "integrity.sqlite3"
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA temp_store=FILE")
        conn.execute("CREATE TABLE observation_map (observation_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL)")
        conn.execute("CREATE TABLE parent_refs (parent_observation_id TEXT NOT NULL, child_trace_id TEXT NOT NULL, child_observation_id TEXT NOT NULL)")
        obs_handle = obs_path.open("w", encoding="utf-8") if use_external_sort else None
        trace_handle = trace_path.open("w", encoding="utf-8") if use_external_sort else None
        observation_batch: list[tuple[str, str]] = []
        parent_batch: list[tuple[str, str, str]] = []

        def flush_batches() -> None:
            nonlocal duplicate_observation_id
            if observation_batch:
                try:
                    conn.executemany(
                        "INSERT INTO observation_map(observation_id, trace_id) VALUES (?, ?)",
                        observation_batch,
                    )
                except sqlite3.IntegrityError:
                    for observation_id, trace_id in observation_batch:
                        try:
                            conn.execute(
                                "INSERT INTO observation_map(observation_id, trace_id) VALUES (?, ?)",
                                (observation_id, trace_id),
                            )
                        except sqlite3.IntegrityError:
                            duplicate_observation_id = duplicate_observation_id or observation_id
                            break
                observation_batch.clear()
            if parent_batch:
                conn.executemany(
                    "INSERT INTO parent_refs(parent_observation_id, child_trace_id, child_observation_id) VALUES (?, ?, ?)",
                    parent_batch,
                )
                parent_batch.clear()
            conn.commit()

        try:
            for row in _iter_ndjson(shard_paths):
                observation_rows += 1
                missing = REQUIRED_OBSERVATION_FIELDS - set(row.keys())
                if missing:
                    errors.append(f"observation row missing fields: {sorted(missing)}")
                    break
                if row.get("parent_observation_id") is None:
                    generation_rows += 1
                if row["observation_id"] == manifest.get("replay_observation_id"):
                    replay_observation_found = True
                if row["trace_id"] == manifest.get("replay_trace_id"):
                    replay_trace_found = True
                observation_batch.append((row["observation_id"], row["trace_id"]))
                if row.get("parent_observation_id"):
                    parent_batch.append((row["parent_observation_id"], row["trace_id"], row["observation_id"]))
                if use_external_sort:
                    obs_handle.write(row["observation_id"] + "\n")
                    trace_handle.write(row["trace_id"] + "\n")
                else:
                    if row["observation_id"] in observation_ids and duplicate_observation_id is None:
                        duplicate_observation_id = row["observation_id"]
                    observation_ids.add(row["observation_id"])
                    trace_ids.add(row["trace_id"])
                if len(observation_batch) >= 10000:
                    flush_batches()
            flush_batches()
        finally:
            if obs_handle is not None:
                obs_handle.close()
            if trace_handle is not None:
                trace_handle.close()

        if use_external_sort and not errors:
            duplicate_output = subprocess.run(
                ["bash", "-lc", f"LC_ALL=C sort '{obs_path}' | uniq -d | head -n 1"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            if duplicate_output:
                duplicate_observation_id = duplicate_output
            trace_count = int(
                subprocess.run(
                    ["bash", "-lc", f"LC_ALL=C sort -u '{trace_path}' | wc -l"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
            )
        else:
            trace_count = len(trace_ids)

        missing_parent = conn.execute(
            """
            SELECT parent_refs.parent_observation_id, parent_refs.child_observation_id
            FROM parent_refs
            LEFT JOIN observation_map ON parent_refs.parent_observation_id = observation_map.observation_id
            WHERE observation_map.observation_id IS NULL
            LIMIT 1
            """
        ).fetchone()
        cross_trace_parent = conn.execute(
            """
            SELECT parent_refs.parent_observation_id, parent_refs.child_observation_id
            FROM parent_refs
            JOIN observation_map ON parent_refs.parent_observation_id = observation_map.observation_id
            WHERE observation_map.trace_id != parent_refs.child_trace_id
            LIMIT 1
            """
        ).fetchone()
        conn.close()

    if duplicate_observation_id:
        errors.append(f"duplicate observation_id detected: {duplicate_observation_id}")
    if missing_parent:
        errors.append(f"missing parent_observation_id detected: {missing_parent[0]} for child {missing_parent[1]}")
    if cross_trace_parent:
        errors.append(
            f"parent/child trace mismatch detected: parent {cross_trace_parent[0]} child {cross_trace_parent[1]}"
        )

    if summary.get("observation_rows") != observation_rows:
        errors.append(
            f"observation_rows mismatch: expected {summary.get('observation_rows')} got {observation_rows}"
        )
    if summary.get("generation_rows") != generation_rows:
        errors.append(
            f"generation_rows mismatch: expected {summary.get('generation_rows')} got {generation_rows}"
        )
    if labels.get("replay_observation_id") != manifest.get("replay_observation_id"):
        errors.append("accuracy_labels replay_observation_id must match manifest replay_observation_id")
    if not replay_observation_found:
        errors.append("manifest replay_observation_id not found in shards")
    if not replay_trace_found:
        errors.append("manifest replay_trace_id not found in shards")
    if summary.get("trace_count") != trace_count:
        errors.append(f"trace_count mismatch: expected {summary.get('trace_count')} got {trace_count}")
    if manifest.get("trace_target") != summary.get("trace_count"):
        errors.append(
            f"manifest trace_target mismatch: expected {manifest.get('trace_target')} got {summary.get('trace_count')}"
        )
    if len(shard_paths) < 2:
        warnings.append("large dataset has fewer than 2 shards")

    return {"ok": not errors, "errors": errors, "warnings": warnings}
