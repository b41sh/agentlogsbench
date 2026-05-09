#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentlogsbench.tooling.generator import generate_dataset_chunk, generate_large_dataset_shard, write_ndjson
from agentlogsbench.tooling.paths import data_generation_path, seed_dir as default_seed_dir_for_root


def split_counts(total: int, parts: int) -> list[int]:
    base = total // parts
    remainder = total % parts
    return [base + (1 if index < remainder else 0) for index in range(parts)]


def compress_shard(path: Path, compression_level: int) -> tuple[Path, int, int]:
    original_size = path.stat().st_size
    compressed_path = path.with_suffix(path.suffix + ".gz")
    with path.open("rb") as source, gzip.open(compressed_path, "wb", compresslevel=compression_level) as target:
        shutil.copyfileobj(source, target)
    compressed_size = compressed_path.stat().st_size
    path.unlink()
    return compressed_path, original_size, compressed_size


def load_tier_defaults(root: Path, tier: str) -> tuple[int, int]:
    payload = json.loads(data_generation_path(root / "agentlogsbench").read_text(encoding="utf-8"))
    tier_payload = payload["tiers"][tier]
    generation_target = (
        tier_payload["generation_rows"]
        if isinstance(tier_payload["generation_rows"], int)
        else tier_payload["generation_rows"]["min"]
    )
    if tier == "S":
        trace_target = round(generation_target * (20 / 48))
    else:
        trace_target = round(generation_target / 2.4)
    return generation_target, trace_target


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a sharded large AI agent observability benchmark dataset.")
    parser.add_argument("--output-dir", type=Path, default=Path("generated/medium"))
    parser.add_argument("--seed-dir", type=Path, default=default_seed_dir_for_root(REPO_ROOT / "agentlogsbench"))
    parser.add_argument("--tier", choices=("S", "M", "L"), default="M")
    parser.add_argument("--generations", type=int)
    parser.add_argument("--traces", type=int)
    parser.add_argument("--chunk-generations", type=int, default=25000)
    parser.add_argument("--seed", type=int, default=20260412)
    parser.add_argument("--call-idx-start", type=int, default=1)
    parser.add_argument("--trace-idx-start", type=int, default=1)
    parser.add_argument("--shard-index-start", type=int, default=0)
    parser.add_argument("--shard-prefix", type=str, default="")
    parser.add_argument("--worker-id", type=str, default="main")
    parser.add_argument("--total-shards-expected", type=int)
    parser.add_argument("--compress-shards", action="store_true")
    parser.add_argument("--compression-level", type=int, default=6)
    parser.add_argument("--log-shard-progress", action="store_true")
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    default_generations, default_traces = load_tier_defaults(REPO_ROOT, args.tier)
    total_generations = args.generations or default_generations
    total_traces = args.traces or default_traces
    if total_generations <= 0 or total_traces <= 0:
        raise SystemExit("generations and traces must be positive")
    shard_count = min((total_generations + args.chunk_generations - 1) // args.chunk_generations, total_traces)
    generation_chunks = split_counts(total_generations, shard_count)
    trace_chunks = split_counts(total_traces, shard_count)

    generation_done = 0
    trace_done = 0
    call_idx_start = args.call_idx_start
    trace_idx_start = args.trace_idx_start
    chunk_id = args.shard_index_start
    source_counter = Counter()
    model_counter = Counter()
    tool_counter = Counter()
    observation_rows = 0
    total_uncompressed_bytes = 0
    total_compressed_bytes = 0
    replay_trace_id = None
    replay_observation_id = None
    shard_specs = []
    total_shards_expected = args.total_shards_expected or shard_count

    for chunk_generations, chunk_traces in zip(generation_chunks, trace_chunks):
        shard_name = f"{args.shard_prefix}agent_observations_{args.tier.lower()}-{chunk_id:05d}.ndjson"
        shard_path = output_dir / shard_name
        shard = generate_large_dataset_shard(
            output_dir=output_dir,
            seed_dir=args.seed_dir,
            generation_target=chunk_generations,
            trace_target=chunk_traces,
            seed=args.seed + chunk_id,
            observation_path=shard_path,
            call_idx_start=call_idx_start,
            trace_idx_start=trace_idx_start,
            edition=f"2026.04-observability-v1-{args.tier}",
        )
        uncompressed_bytes = shard_path.stat().st_size
        compressed_bytes = uncompressed_bytes
        if args.compress_shards:
            shard_path, uncompressed_bytes, compressed_bytes = compress_shard(shard_path, args.compression_level)
            shard_name = shard_path.name
        total_uncompressed_bytes += uncompressed_bytes
        total_compressed_bytes += compressed_bytes

        generation_done += shard.summary["generation_rows"]
        trace_done += shard.summary["trace_count"]
        observation_rows += shard.summary["observation_rows"]
        call_idx_start += shard.summary["generation_rows"]
        trace_idx_start += shard.summary["trace_count"]
        source_counter.update(shard.summary.get("source_distribution", {}))
        model_counter.update(shard.summary.get("model_distribution", {}))
        tool_counter.update(shard.summary.get("tool_name_distribution", {}))
        replay_trace_id = replay_trace_id or shard.manifest["replay_trace_id"]
        replay_observation_id = replay_observation_id or shard.manifest["replay_observation_id"]
        shard_specs.append(
            {
                "path": shard_name,
                "file_number": chunk_id + 1,
                "generation_rows": shard.summary["generation_rows"],
                "observation_rows": shard.summary["observation_rows"],
                "trace_count": shard.summary["trace_count"],
                "seed": args.seed + chunk_id,
                "compression": "gzip" if args.compress_shards else "none",
                "uncompressed_bytes": uncompressed_bytes,
                "compressed_bytes": compressed_bytes,
            }
        )
        if args.log_shard_progress:
            print(
                json.dumps(
                    {
                        "event": "shard_complete",
                        "worker_id": args.worker_id,
                        "file_number": chunk_id + 1,
                        "total_files": total_shards_expected,
                        "path": shard_name,
                        "generation_rows": shard.summary["generation_rows"],
                        "observation_rows": shard.summary["observation_rows"],
                        "trace_count": shard.summary["trace_count"],
                        "uncompressed_bytes": uncompressed_bytes,
                        "compressed_bytes": compressed_bytes,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
        chunk_id += 1

    summary = {
        "generation_rows": generation_done,
        "observation_rows": observation_rows,
        "trace_count": trace_done,
        "source_distribution": dict(source_counter),
        "model_distribution": dict(model_counter),
        "tool_name_distribution": dict(tool_counter),
        "shard_count": len(shard_specs),
        "chunk_generations": args.chunk_generations,
        "compression": "gzip" if args.compress_shards else "none",
        "uncompressed_bytes": total_uncompressed_bytes,
        "compressed_bytes": total_compressed_bytes,
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
            f"agent_observations_{args.tier.lower()}-*.ndjson.gz"
            if args.compress_shards
            else f"agent_observations_{args.tier.lower()}-*.ndjson"
        ),
        "observation_files": shard_specs,
        "replay_trace_id": replay_trace_id,
        "replay_observation_id": replay_observation_id,
        "compression": "gzip" if args.compress_shards else "none",
    }
    labels = {
        "version": 1,
        "replay_observation_id": replay_observation_id,
        "top_models": [item[0] for item in model_counter.most_common(5)],
    }

    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / "accuracy_labels.json").write_text(json.dumps(labels, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "output_dir": str(output_dir),
                "generation_rows": generation_done,
                "observation_rows": observation_rows,
                "shards": len(shard_specs),
                "trace_rows": trace_done,
                "compression": summary["compression"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
