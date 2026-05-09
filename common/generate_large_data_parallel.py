#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentlogsbench.common.generate_large_data import load_tier_defaults
from agentlogsbench.tooling.paths import seed_dir as default_seed_dir_for_root


def split_counts(total: int, parts: int) -> list[int]:
    base = total // parts
    remainder = total % parts
    return [base + (1 if index < remainder else 0) for index in range(parts)]


def format_bytes(size: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    value = float(size)
    unit = units[0]
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            break
        value /= 1024.0
    return f"{value:.2f}{unit}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run sharded large benchmark generation with multiple workers.")
    parser.add_argument("--output-dir", type=Path, default=Path("generated/medium_parallel"))
    parser.add_argument("--seed-dir", type=Path, default=default_seed_dir_for_root(REPO_ROOT / "agentlogsbench"))
    parser.add_argument("--tier", choices=("S", "M", "L"), default="M")
    parser.add_argument("--generations", type=int)
    parser.add_argument("--traces", type=int)
    parser.add_argument("--chunk-generations", type=int, default=25000)
    parser.add_argument("--workers", type=int, default=max(1, os.cpu_count() or 1))
    parser.add_argument("--seed", type=int, default=20260412)
    parser.add_argument("--compress-shards", action="store_true")
    parser.add_argument("--compression-level", type=int, default=6)
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    if (output_dir / "workers").exists():
        shutil.rmtree(output_dir / "workers")
    for path in output_dir.glob("w*-agent_observations_*.ndjson"):
        path.unlink()
    for path in output_dir.glob("w*-agent_observations_*.ndjson.gz"):
        path.unlink()
    for path in (output_dir / "summary.json", output_dir / "manifest.json", output_dir / "accuracy_labels.json"):
        if path.exists():
            path.unlink()
    default_generations, default_traces = load_tier_defaults(REPO_ROOT, args.tier)
    total_generations = args.generations or default_generations
    total_traces = args.traces or default_traces

    total_shards_expected = max(1, (total_generations + args.chunk_generations - 1) // args.chunk_generations)
    shard_splits = split_counts(total_shards_expected, args.workers)
    generation_chunks = split_counts(total_generations, total_shards_expected)
    trace_chunks = split_counts(total_traces, total_shards_expected)

    call_idx_start = 1
    trace_idx_start = 1
    shard_index_start = 0
    worker_dirs: list[Path] = []
    procs = []
    progress_lock = threading.Lock()
    progress = {
        "files_completed": 0,
        "generation_rows": 0,
        "observation_rows": 0,
        "trace_count": 0,
        "uncompressed_bytes": 0,
        "compressed_bytes": 0,
    }

    chunk_cursor = 0
    for worker_id, worker_shards in enumerate(shard_splits):
        worker_generations = sum(generation_chunks[chunk_cursor : chunk_cursor + worker_shards])
        worker_traces = sum(trace_chunks[chunk_cursor : chunk_cursor + worker_shards])
        worker_dir = output_dir / "workers" / f"worker-{worker_id:02d}"
        worker_dir.mkdir(parents=True, exist_ok=True)
        worker_dirs.append(worker_dir)
        cmd = [
            "python3",
            str(REPO_ROOT / "agentlogsbench" / "common" / "generate_large_data.py"),
            "--output-dir",
            str(worker_dir),
            "--seed-dir",
            str(args.seed_dir),
            "--tier",
            args.tier,
            "--generations",
            str(worker_generations),
            "--traces",
            str(worker_traces),
            "--chunk-generations",
            str(args.chunk_generations),
            "--seed",
            str(args.seed + worker_id * 100000),
            "--call-idx-start",
            str(call_idx_start),
            "--trace-idx-start",
            str(trace_idx_start),
            "--shard-index-start",
            str(shard_index_start),
            "--shard-prefix",
            f"w{worker_id:02d}-",
            "--worker-id",
            f"worker-{worker_id:02d}",
            "--total-shards-expected",
            str(total_shards_expected),
            "--log-shard-progress",
        ]
        if args.compress_shards:
            cmd.extend(
                [
                    "--compress-shards",
                    "--compression-level",
                    str(args.compression_level),
                ]
            )
        procs.append(
            (
                worker_id,
                subprocess.Popen(
                    cmd,
                    cwd=REPO_ROOT,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                ),
            )
        )
        call_idx_start += worker_generations
        trace_idx_start += worker_traces
        shard_index_start += worker_shards
        chunk_cursor += worker_shards

    def stream_worker_output(worker_id: int, proc: subprocess.Popen[str]) -> None:
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            line = raw_line.rstrip("\n")
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                print(f"[worker-{worker_id:02d}] {line}", flush=True)
                continue
            if payload.get("event") != "shard_complete":
                print(json.dumps(payload, ensure_ascii=False), flush=True)
                continue
            with progress_lock:
                progress["files_completed"] += 1
                progress["generation_rows"] += int(payload.get("generation_rows", 0))
                progress["observation_rows"] += int(payload.get("observation_rows", 0))
                progress["trace_count"] += int(payload.get("trace_count", 0))
                progress["uncompressed_bytes"] += int(payload.get("uncompressed_bytes", 0))
                progress["compressed_bytes"] += int(payload.get("compressed_bytes", 0))
                files_completed = progress["files_completed"]
                generation_done = progress["generation_rows"]
                uncompressed_total = progress["uncompressed_bytes"]
                compressed_total = progress["compressed_bytes"]
            ratio = (
                compressed_total / uncompressed_total
                if uncompressed_total
                else 1.0
            )
            print(
                (
                    "[progress] "
                    f"file {payload['file_number']}/{payload['total_files']} "
                    f"({payload['path']}) "
                    f"raw={format_bytes(int(payload['uncompressed_bytes']))} "
                    f"gz={format_bytes(int(payload['compressed_bytes']))} "
                    f"done_files={files_completed}/{total_shards_expected} "
                    f"done_generations={generation_done}/{total_generations} "
                    f"total_raw={format_bytes(uncompressed_total)} "
                    f"total_gz={format_bytes(compressed_total)} "
                    f"ratio={ratio:.2%}"
                ),
                flush=True,
            )

    threads = [
        threading.Thread(target=stream_worker_output, args=(worker_id, proc), daemon=True)
        for worker_id, proc in procs
    ]
    for thread in threads:
        thread.start()

    for worker_id, proc in procs:
        code = proc.wait()
        if code != 0:
            raise SystemExit(f"worker {worker_id} failed with exit code {code}")
    for thread in threads:
        thread.join()

    combined_source = Counter()
    combined_models = Counter()
    combined_tools = Counter()
    combined_observation_rows = 0
    combined_generation_rows = 0
    combined_trace_rows = 0
    combined_uncompressed_bytes = 0
    combined_compressed_bytes = 0
    combined_shards = []
    replay_trace_id = None
    replay_observation_id = None
    for worker_dir in worker_dirs:
        manifest = json.loads((worker_dir / "manifest.json").read_text(encoding="utf-8"))
        summary = json.loads((worker_dir / "summary.json").read_text(encoding="utf-8"))
        combined_source.update(summary.get("source_distribution", {}))
        combined_models.update(summary.get("model_distribution", {}))
        combined_tools.update(summary.get("tool_name_distribution", {}))
        combined_observation_rows += summary["observation_rows"]
        combined_generation_rows += summary["generation_rows"]
        combined_trace_rows += summary["trace_count"]
        combined_uncompressed_bytes += int(summary.get("uncompressed_bytes", 0))
        combined_compressed_bytes += int(summary.get("compressed_bytes", 0))
        replay_trace_id = replay_trace_id or manifest["replay_trace_id"]
        replay_observation_id = replay_observation_id or manifest["replay_observation_id"]
        for shard in manifest["observation_files"]:
            shard_path = worker_dir / shard["path"]
            target_name = shard_path.name
            target_path = output_dir / target_name
            if target_path.exists():
                raise SystemExit(f"duplicate shard target: {target_path}")
            shutil.move(str(shard_path), str(target_path))
            combined_shards.append({**shard, "path": target_name})

    summary = {
        "generation_rows": combined_generation_rows,
        "observation_rows": combined_observation_rows,
        "trace_count": combined_trace_rows,
        "source_distribution": dict(combined_source),
        "model_distribution": dict(combined_models),
        "tool_name_distribution": dict(combined_tools),
        "shard_count": len(combined_shards),
        "worker_count": args.workers,
        "chunk_generations": args.chunk_generations,
        "compression": "gzip" if args.compress_shards else "none",
        "uncompressed_bytes": combined_uncompressed_bytes,
        "compressed_bytes": combined_compressed_bytes,
    }
    manifest = {
        "edition": f"2026.04-observability-v1-{args.tier}",
        "dataset_tier": args.tier,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "seed": args.seed,
        "seed_files": sorted(str(path.relative_to(args.seed_dir)) for path in args.seed_dir.rglob("*.json")),
        "trace_target": total_traces,
        "generation_target": total_generations,
        "summary_file": "summary.json",
        "accuracy_labels_file": "accuracy_labels.json",
        "observation_glob": (
            f"w*-agent_observations_{args.tier.lower()}-*.ndjson.gz"
            if args.compress_shards
            else f"w*-agent_observations_{args.tier.lower()}-*.ndjson"
        ),
        "observation_files": combined_shards,
        "replay_trace_id": replay_trace_id,
        "replay_observation_id": replay_observation_id,
        "worker_count": args.workers,
        "compression": "gzip" if args.compress_shards else "none",
    }
    labels = {
        "version": 1,
        "replay_observation_id": replay_observation_id,
        "top_models": [item[0] for item in combined_models.most_common(5)],
    }

    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / "accuracy_labels.json").write_text(json.dumps(labels, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "output_dir": str(output_dir),
                "generation_rows": combined_generation_rows,
                "observation_rows": combined_observation_rows,
                "shards": len(combined_shards),
                "workers": args.workers,
                "compression": summary["compression"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
