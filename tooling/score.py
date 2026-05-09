from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List

from agentlogsbench.tooling.engines import CLICKBENCH_RESULTS_DIRNAME, LEGACY_RESULTS_DIRNAME


RESULT_STATUSES = {"ok", "incorrect", "timeout", "unsupported"}
EXPECTED_EDITION = "2026.04-observability-v1"
EXPECTED_WARMUP_RUNS = 1
EXPECTED_MEASURED_RUNS = 5
EXPECTED_TIMEOUT_SECONDS = 900
RUNNABLE_EXECUTION_MODE = "runnable"


def load_result(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_result_files(results_dir: Path) -> Iterable[Path]:
    direct = sorted(results_dir.glob("*.json"))
    legacy_nested = sorted(results_dir.glob(f"*/result.json"))
    clickbench_nested = sorted(results_dir.glob(f"*/{CLICKBENCH_RESULTS_DIRNAME}/*.json"))
    seen = set()
    for path in direct + legacy_nested + clickbench_nested:
        if path not in seen:
            seen.add(path)
            yield path


def query_latency_ms(query_result: Dict[str, Any], measured_runs: int) -> float:
    runs = query_result.get("latency_ms_runs")
    if not isinstance(runs, list) or len(runs) != measured_runs:
        raise ValueError(f"expected latency_ms_runs with exactly {measured_runs} entries: {query_result}")
    return float(median(runs))


def geometric_mean(values: List[float]) -> float:
    if not values:
        raise ValueError("geometric_mean requires at least one value")
    return math.exp(sum(math.log(value) for value in values) / len(values))


def query_results_by_id(result: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {item["query_id"]: item for item in result["query_results"]}


def append_engine_status(
    appendix: List[Dict[str, Any]],
    engine: str,
    status: str,
    reason: str,
) -> None:
    appendix.append({
        "engine": engine,
        "status": status,
        "reason": reason,
    })


def score_results(results: List[Dict[str, Any]], query_ids: List[str]) -> Dict[str, Any]:
    by_engine: Dict[str, Dict[str, Any]] = {}
    appendix: List[Dict[str, Any]] = []
    eligible_results: Dict[str, Dict[str, Any]] = {}

    for result in results:
        engine = result["engine"]
        by_engine[engine] = result

    for engine, result in sorted(by_engine.items()):
        if result.get("edition") != EXPECTED_EDITION:
            append_engine_status(
                appendix,
                engine,
                "incomplete",
                f"edition mismatch: {result.get('edition')}",
            )
            continue
        if result.get("dataset_tier") != "M":
            append_engine_status(
                appendix,
                engine,
                "supporting_tier",
                f"dataset_tier={result.get('dataset_tier')}, main leaderboard is M only",
            )
            continue

        execution_mode = result.get("run_metadata", {}).get("execution_mode")
        if execution_mode != RUNNABLE_EXECUTION_MODE:
            append_engine_status(
                appendix,
                engine,
                "non_runnable",
                f"execution_mode={execution_mode or 'missing'}, main leaderboard requires runnable results",
            )
            continue

        per_query = query_results_by_id(result)
        missing = [qid for qid in query_ids if qid not in per_query]
        if missing:
            append_engine_status(
                appendix,
                engine,
                "incomplete",
                f"missing queries: {', '.join(missing)}",
            )
            continue

        run_protocol = result.get("run_protocol", {})
        if (
            run_protocol.get("warmup_runs") != EXPECTED_WARMUP_RUNS
            or run_protocol.get("measured_runs") != EXPECTED_MEASURED_RUNS
        ):
            append_engine_status(
                appendix,
                engine,
                "incomplete",
                "run protocol mismatch: expected warmup_runs=1 and measured_runs=5",
            )
            continue
        if run_protocol.get("timeout_seconds") != EXPECTED_TIMEOUT_SECONDS:
            append_engine_status(
                appendix,
                engine,
                "incomplete",
                "run protocol mismatch: expected timeout_seconds=900",
            )
            continue

        non_ok = [qid for qid in query_ids if per_query[qid]["status"] != "ok"]
        if non_ok:
            append_engine_status(
                appendix,
                engine,
                "incomplete",
                f"non-ok queries: {', '.join(non_ok)}",
            )
            continue

        try:
            for qid in query_ids:
                status = per_query[qid].get("status")
                if status not in RESULT_STATUSES:
                    raise ValueError(f"invalid status for {engine}/{qid}: {status}")
                query_latency_ms(per_query[qid], run_protocol["measured_runs"])
        except ValueError as exc:
            append_engine_status(appendix, engine, "incomplete", str(exc))
            continue

        eligible_results[engine] = result

    fastest_by_query: Dict[str, float] = {}
    for engine, result in eligible_results.items():
        per_query = query_results_by_id(result)
        measured_runs = result["run_protocol"]["measured_runs"]
        for qid in query_ids:
            latency = query_latency_ms(per_query[qid], measured_runs)
            fastest_by_query[qid] = min(latency, fastest_by_query.get(qid, latency))

    leaderboard = []
    for engine, result in sorted(by_engine.items()):
        if engine not in eligible_results:
            continue
        per_query = query_results_by_id(result)
        run_protocol = result.get("run_protocol", {})
        ratios = []
        per_query_scores = {}
        for qid in query_ids:
            latency = query_latency_ms(per_query[qid], run_protocol["measured_runs"])
            fastest = fastest_by_query[qid]
            ratio = latency / fastest
            per_query_scores[qid] = {
                "latency_ms": latency,
                "fastest_ms": fastest,
                "ratio": ratio,
            }
            ratios.append(ratio)

        composite = geometric_mean(ratios)
        secondary = result.get("secondary_metrics", {})
        leaderboard.append({
            "engine": engine,
            "dataset_tier": result.get("dataset_tier"),
            "composite_ratio": composite,
            "per_query": per_query_scores,
            "secondary_metrics": secondary,
        })

    leaderboard.sort(key=lambda item: item["composite_ratio"])
    return {
        "main_leaderboard": leaderboard,
        "appendix": appendix,
        "fastest_by_query": fastest_by_query,
    }


def load_and_score(results_dir: Path, query_ids: List[str]) -> Dict[str, Any]:
    results = []
    for path in iter_result_files(results_dir):
        payload = load_result(path)
        if "query_results" in payload:
            results.append(payload)
    return score_results(results, query_ids)
