#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple
from urllib import error as urllib_error
from urllib import request as urllib_request

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentlogsbench.tooling.query_results import (
    fingerprint_query_rows,
    fingerprint_query_rows_excluding_fields,
    normalize_query_rows,
)
from agentlogsbench.tooling.paths import (
    adapter_manifest_path,
    adapter_query_map_path,
    bundled_small_data_dir,
    edition_path,
    query_contracts_path,
    query_suite_path,
)
from agentlogsbench.tooling.query_context import load_context_from_paths, load_manifest, manifest_observation_paths


TEXT_FIELDS = ["input", "output"]
Q05_TEXT_SCORE_TOKENS = ("unable", "open")
Q08_TEXT_SCORE_TOKENS = ("unable", "open")
QUERY_FIELDS: Dict[str, List[str]] = {
    "Q01": ["event_time", "trace_id", "observation_id", "seq_no", "type", "status", "model", "tool_name", "latency_ms"],
    "Q02": ["trace_id", "started_at", "observation_count", "failure_count", "total_cost", "total_latency_ms"],
    "Q03": ["trace_id", "seq_no", "type", "status", "model", "tool_name", "input", "output"],
    "Q04": ["trace_id", "seq_no", "observation_id", "parent_observation_id", "parent_type", "child_type", "status", "tool_name"],
    "Q05": ["event_time", "trace_id", "observation_id", "tool_name", "latency_ms", "text_score", "payload"],
    "Q06": ["type", "model", "observations", "input_tokens", "output_tokens", "total_cost", "avg_latency_ms"],
    "Q07": ["event_time", "trace_id", "observation_id", "type", "status", "payload"],
    "Q08": ["event_time", "trace_id", "observation_id", "type", "status", "input", "output", "phrase_match", "text_score"],
    "Q09": ["tool_name", "status", "observations", "avg_latency_ms"],
    "Q10": ["stop_reason", "cache_hit", "observations", "avg_latency_ms"],
    "Q11": ["event_time", "trace_id", "observation_id", "type", "status", "tool_name", "latency_ms", "phrase_match", "text_score"],
    "Q12": ["release_ring", "customer_tier", "retrieval_strategy", "observations", "avg_latency_ms", "total_cost"],
    "Q13": ["observations", "traces", "last_event_time"],
    "Q14": ["event_time", "trace_id", "observation_id", "type", "status", "tool_name"],
    "Q15": ["event_time", "trace_id", "observation_id", "type", "status", "tool_name", "latency_ms"],
    "Q16": ["event_time", "trace_id", "observation_id", "type", "status", "release_ring", "customer_tier", "traffic_cluster"],
    "Q17": ["trace_id", "observation_id", "seq_no", "type", "status", "request_key", "workflow_variant"],
    "Q18": ["prompt_template_version", "observations", "traces", "avg_latency_ms", "total_cost"],
    "Q19": ["deployment_channel", "release_ring", "incident_observations", "incident_traces", "avg_latency_ms"],
    "Q20": ["workflow_variant", "policy_pack", "observations", "tenants", "avg_latency_ms", "total_cost"],
}
TOKEN_PATTERNS = {
    token: re.compile(rf"(?<![0-9A-Za-z_]){re.escape(token)}(?![0-9A-Za-z_])", re.IGNORECASE)
    for token in sorted(set(Q05_TEXT_SCORE_TOKENS + Q08_TEXT_SCORE_TOKENS))
}


def search_engine_slug() -> str:
    slug = os.environ.get("AIBENCH_SEARCH_ENGINE", "elastic").strip().lower()
    return slug or "elastic"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def env_flag(name: str) -> bool:
    return os.environ.get(name, "0").lower() in {"1", "true", "yes"}


def storage_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for sub in path.rglob("*"):
        if sub.is_file():
            total += sub.stat().st_size
    return total


def load_query_definitions(agentlogsbench_root: Path) -> List[Dict[str, Any]]:
    suite = json.loads(query_suite_path(agentlogsbench_root).read_text(encoding="utf-8"))
    return list(suite["queries"])


def verify_contract(
    contract: Dict[str, Any],
    rows: List[Dict[str, Any]],
    observed_fields: List[str],
) -> Tuple[List[str], List[str], str]:
    row_count = len(rows)
    required_fields = contract["assertions"].get("must_include_fields", [])
    missing_fields = [field for field in required_fields if field not in observed_fields]
    row_count_errors: List[str] = []
    minimum_row_count = contract.get("minimum_row_count")
    if isinstance(minimum_row_count, int) and row_count < minimum_row_count:
        row_count_errors.append(f"row_count {row_count} < minimum_row_count {minimum_row_count}")
    expected_row_count = contract.get("expected_row_count")
    if isinstance(expected_row_count, int) and row_count != expected_row_count:
        row_count_errors.append(f"row_count {row_count} != expected_row_count {expected_row_count}")
    if contract.get("result_kind") == "sample_rows" and "payload" not in contract["assertions"].get("must_include_fields", []):
        return missing_fields, row_count_errors, fingerprint_query_rows_excluding_fields(rows, ["payload"])
    return missing_fields, row_count_errors, fingerprint_query_rows(rows)


def render_query_log(query_id: str, body: Dict[str, Any], rows: List[Dict[str, Any]], runs: List[int]) -> str:
    return (
        f"{query_id}\n"
        f"{json.dumps(body, ensure_ascii=False, indent=2)}\n"
        f"{json.dumps(rows, ensure_ascii=False, indent=2)}\n"
        f"latency_ms_runs={runs}\n\n"
    )


def extract_source(hit: Dict[str, Any]) -> Dict[str, Any]:
    return dict(hit.get("_source", {}))


def attr_value(source: Dict[str, Any], key: str) -> Any:
    payload = source.get("payload", {})
    if not isinstance(payload, dict):
        return None
    attr = payload.get("attr", {})
    if not isinstance(attr, dict):
        return None
    return attr.get(key)


def combined_text(source: Dict[str, Any]) -> str:
    parts = [
        source.get("input") or "",
        source.get("output") or "",
    ]
    return " ".join(parts).lower()


def text_score(source: Dict[str, Any], tokens: Tuple[str, ...]) -> int:
    text = combined_text(source)
    return sum(1 for token in tokens if TOKEN_PATTERNS[token].search(text))


def phrase_match(source: Dict[str, Any]) -> int:
    text = combined_text(source)
    return int("unable to open" in text)


def ordered_fields(query_id: str, rows: List[Dict[str, Any]]) -> List[str]:
    fields = QUERY_FIELDS[query_id]
    if rows:
        seen = set()
        ordered: List[str] = []
        for field in fields:
            if field in rows[0]:
                ordered.append(field)
                seen.add(field)
        for row in rows:
            for field in row:
                if field not in seen:
                    ordered.append(field)
                    seen.add(field)
        return ordered
    return list(fields)


def json_request(method: str, url: str, payload: Dict[str, Any] | None = None, timeout: int = 30) -> Dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib_request.Request(url, data=data, headers=headers, method=method)
    with urllib_request.urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else {}


def search(endpoint: str, index: str, body: Dict[str, Any], timeout_seconds: int) -> Tuple[Dict[str, Any], int]:
    started = time.perf_counter()
    response = json_request("POST", f"{endpoint}/{index}/_search", payload=body, timeout=timeout_seconds)
    elapsed_ms = max(1, int((time.perf_counter() - started) * 1000))
    return response, elapsed_ms


def numeric_value(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def stable_num(value: Any) -> float:
    return float(value) if value is not None else 0.0


def stable_text(value: Any) -> str:
    return str(value) if value is not None else ""


def bucket_rows(buckets: Iterable[Dict[str, Any]], mapper: Any) -> List[Dict[str, Any]]:
    return [mapper(bucket) for bucket in buckets]


def q01_body(params: Dict[str, str]) -> Dict[str, Any]:
    return {
        "size": 50,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"tenant": params["tenant"]}},
                    {"range": {"biz_date": {"gte": params["start_date"], "lte": params["end_date"]}}},
                    {"terms": {"type": ["GENERATION", "TOOL"]}},
                    {"terms": {"status": ["ok", "error"]}},
                ]
            }
        },
        "sort": [{"event_time": {"order": "desc"}}, {"seq_no": {"order": "desc"}}],
        "_source": QUERY_FIELDS["Q01"],
    }


def q02_body(params: Dict[str, str]) -> Dict[str, Any]:
    return {
        "size": 0,
        "query": {"range": {"biz_date": {"gte": params["start_date"], "lte": params["end_date"]}}},
        "aggs": {
            "trace_id": {
                "terms": {"field": "trace_id", "size": 100, "order": {"total_cost": "desc"}},
                "aggs": {
                    "started_at": {"min": {"field": "event_time", "format": "yyyy-MM-dd HH:mm:ss"}},
                    "failure_count": {"filter": {"bool": {"must_not": [{"term": {"status": "ok"}}]}}},
                    "total_cost": {"sum": {"field": "total_cost"}},
                    "total_latency_ms": {"sum": {"field": "latency_ms"}},
                },
            }
        },
    }


def q03_body(params: Dict[str, str]) -> Dict[str, Any]:
    return {
        "size": 100,
        "query": {"term": {"trace_id": params["trace_id"]}},
        "sort": [{"seq_no": {"order": "asc"}}],
        "_source": QUERY_FIELDS["Q03"],
    }


def q04_body(params: Dict[str, str]) -> Dict[str, Any]:
    return {
        "size": 200,
        "query": {"term": {"trace_id": params["trace_id"]}},
        "sort": [{"seq_no": {"order": "asc"}}],
        "_source": ["trace_id", "seq_no", "observation_id", "parent_observation_id", "type", "status", "tool_name"],
    }


def q05_body(params: Dict[str, str]) -> Dict[str, Any]:
    return {
        "size": 50,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"type": "TOOL"}},
                    {"term": {"status": "error"}},
                    {"term": {"tenant": params["tenant"]}},
                    {"term": {"app": params["app"]}},
                ],
                "must": [
                    {
                        "multi_match": {
                            "query": "unable open",
                            "fields": TEXT_FIELDS,
                            "type": "cross_fields",
                            "operator": "and",
                        }
                    }
                ],
            }
        },
        "sort": [
            {"latency_ms": {"order": "desc"}},
            {"event_time": {"order": "desc"}},
        ],
        "_source": ["event_time", "trace_id", "observation_id", "tool_name", "latency_ms", "payload", "input", "output"],
    }


def q06_body() -> Dict[str, Any]:
    return {
        "size": 0,
        "aggs": {
            "type": {
                "terms": {"field": "type", "size": 50},
                "aggs": {
                    "model": {
                        "terms": {"field": "model", "size": 50},
                        "aggs": {
                            "input_tokens": {"sum": {"field": "input_tokens"}},
                            "output_tokens": {"sum": {"field": "output_tokens"}},
                            "total_cost": {"sum": {"field": "total_cost"}},
                            "avg_latency_ms": {"avg": {"field": "latency_ms"}},
                        },
                    }
                },
            }
        },
    }


def q07_body() -> Dict[str, Any]:
    return {
        "size": 50,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"environment": "prod"}},
                    {"terms": {"type": ["GENERATION", "TOOL", "RETRIEVAL"]}},
                    {"terms": {"payload.attr.release_ring": ["stable", "canary"]}},
                    {"terms": {"payload.attr.retrieval_strategy": ["hybrid", "hybrid_rerank"]}},
                    {"terms": {"payload.attr.surface": ["api", "workflow_runner"]}},
                    {
                        "terms": {
                            "payload.attr.prompt_template_version": [
                                "pt_2026_03_2",
                                "pt_2026_04_1",
                                "pt_2026_04_2",
                            ]
                        }
                    },
                ]
            }
        },
        "sort": [
            {"event_time": {"order": "desc"}},
            {"trace_id": {"order": "desc"}},
            {"observation_id": {"order": "desc"}},
        ],
        "_source": QUERY_FIELDS["Q07"],
    }


def q08_body(params: Dict[str, str]) -> Dict[str, Any]:
    return {
        "size": 50,
        "query": {
            "bool": {
                "filter": [{"term": {"tenant": params["tenant"]}}],
                "must": [
                    {
                        "multi_match": {
                            "query": "unable open",
                            "fields": TEXT_FIELDS,
                            "type": "cross_fields",
                            "operator": "and",
                        }
                    },
                    {
                        "multi_match": {
                            "query": "unable to open",
                            "fields": TEXT_FIELDS,
                            "type": "phrase",
                        }
                    }
                ],
            }
        },
        "sort": [
            {"event_time": {"order": "desc"}},
            {"trace_id": {"order": "desc"}},
            {"observation_id": {"order": "desc"}},
        ],
        "highlight": {"fields": {"input": {}, "output": {}}},
        "_source": ["event_time", "trace_id", "observation_id", "type", "status", "input", "output", "payload"],
    }


def q09_body() -> Dict[str, Any]:
    return {
        "size": 0,
        "query": {"term": {"type": "TOOL"}},
        "aggs": {
            "tool_name": {
                "terms": {"field": "tool_name", "size": 100},
                "aggs": {
                    "status": {
                        "terms": {"field": "status", "size": 10},
                        "aggs": {"avg_latency_ms": {"avg": {"field": "latency_ms"}}},
                    }
                },
            }
        },
    }


def q10_body() -> Dict[str, Any]:
    return {
        "size": 0,
        "query": {"term": {"type": "GENERATION"}},
        "aggs": {
            "stop_reason": {
                "terms": {"field": "payload.provider.stop_reason", "size": 20},
                "aggs": {
                    "cache_hit": {
                        "terms": {"field": "payload.provider.cache_hit", "size": 2},
                        "aggs": {"avg_latency_ms": {"avg": {"field": "latency_ms"}}},
                    }
                },
            }
        },
    }


def q11_body(params: Dict[str, str]) -> Dict[str, Any]:
    return {
        "size": 50,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"tenant": params["tenant"]}},
                    {"term": {"app": params["app"]}},
                    {"terms": {"type": ["GENERATION", "TOOL", "RETRIEVAL"]}},
                ],
                "must": [
                    {
                        "multi_match": {
                            "query": "unable open",
                            "fields": TEXT_FIELDS,
                            "type": "cross_fields",
                            "operator": "and",
                        }
                    },
                    {
                        "multi_match": {
                            "query": "unable to open",
                            "fields": TEXT_FIELDS,
                            "type": "phrase",
                        }
                    }
                ],
            }
        },
        "sort": [
            {"latency_ms": {"order": "desc"}},
            {"event_time": {"order": "desc"}},
            {"trace_id": {"order": "desc"}},
            {"observation_id": {"order": "desc"}},
        ],
        "_source": ["event_time", "trace_id", "observation_id", "type", "status", "tool_name", "latency_ms", "input", "output", "payload"],
    }


def q12_body() -> Dict[str, Any]:
    return {
        "size": 0,
        "query": {"terms": {"type": ["GENERATION", "TOOL", "RETRIEVAL"]}},
        "aggs": {
            "release_ring": {
                "terms": {"field": "payload.attr.release_ring", "size": 10},
                "aggs": {
                    "customer_tier": {
                        "terms": {"field": "payload.attr.customer_tier", "size": 10},
                        "aggs": {
                            "retrieval_strategy": {
                                "terms": {"field": "payload.attr.retrieval_strategy", "size": 10},
                                "aggs": {
                                    "avg_latency_ms": {"avg": {"field": "latency_ms"}},
                                    "total_cost": {"sum": {"field": "total_cost"}},
                                },
                            }
                        },
                    }
                },
            }
        },
    }


def q13_body(params: Dict[str, str]) -> Dict[str, Any]:
    return {
        "size": 0,
        "track_total_hits": True,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"tenant": params["tenant"]}},
                    {"range": {"biz_date": {"gte": params["start_date"], "lte": params["end_date"]}}},
                    {"terms": {"type": ["GENERATION", "TOOL", "RETRIEVAL", "EVENT"]}},
                ],
                "must": [
                    {
                        "bool": {
                            "should": [
                                {
                                    "multi_match": {
                                        "query": "timeout awaiting headers",
                                        "fields": TEXT_FIELDS,
                                        "type": "phrase",
                                    }
                                },
                                {
                                    "multi_match": {
                                        "query": "retry budget depleted",
                                        "fields": TEXT_FIELDS,
                                        "type": "phrase",
                                    }
                                },
                                {
                                    "multi_match": {
                                        "query": "transient upstream failure",
                                        "fields": TEXT_FIELDS,
                                        "type": "phrase",
                                    }
                                },
                            ],
                            "minimum_should_match": 1,
                        }
                    }
                ],
            }
        },
        "aggs": {
            "traces": {"cardinality": {"field": "trace_id"}},
            "last_event_time": {"max": {"field": "event_time", "format": "yyyy-MM-dd HH:mm:ss"}},
        },
    }


def q14_body(params: Dict[str, str]) -> Dict[str, Any]:
    return {
        "size": 50,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"tenant": params["tenant"]}},
                    {"term": {"app": params["app"]}},
                    {"terms": {"type": ["GENERATION", "TOOL", "EVENT"]}},
                ],
                "must": [
                    {
                        "bool": {
                            "should": [
                                {"match": {"input": {"query": "deployment"}}},
                                {"match": {"output": {"query": "deployment"}}},
                                {"match": {"input": {"query": "rollback"}}},
                                {"match": {"output": {"query": "rollback"}}},
                                {"match": {"output": {"query": "transient"}}},
                            ],
                            "minimum_should_match": 1,
                        }
                    }
                ],
            }
        },
        "sort": [
            {"event_time": {"order": "desc"}},
            {"trace_id": {"order": "desc"}},
            {"observation_id": {"order": "desc"}},
        ],
        "_source": ["event_time", "trace_id", "observation_id", "type", "status", "tool_name", "output"],
    }


def q15_body(params: Dict[str, str]) -> Dict[str, Any]:
    return {
        "size": 50,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"tenant": params["tenant"]}},
                    {"terms": {"type": ["GENERATION", "TOOL", "RETRIEVAL", "EVENT"]}},
                ],
                "should": [
                    {
                        "multi_match": {
                            "query": "transient upstream failure",
                            "fields": TEXT_FIELDS,
                            "type": "phrase",
                        }
                    },
                    {
                        "multi_match": {
                            "query": "retry budget depleted",
                            "fields": TEXT_FIELDS,
                            "type": "phrase",
                        }
                    },
                    {
                        "multi_match": {
                            "query": "connector timeout",
                            "fields": TEXT_FIELDS,
                            "type": "phrase",
                        }
                    },
                ],
                "minimum_should_match": 1,
            }
        },
        "sort": [
            {"latency_ms": {"order": "desc"}},
            {"event_time": {"order": "desc"}},
            {"trace_id": {"order": "desc"}},
            {"observation_id": {"order": "desc"}},
        ],
        "_source": ["event_time", "trace_id", "observation_id", "type", "status", "tool_name", "latency_ms"],
    }


def q16_body(params: Dict[str, str]) -> Dict[str, Any]:
    return {
        "size": 50,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"tenant": params["tenant"]}},
                    {"term": {"environment": "prod"}},
                    {"terms": {"type": ["GENERATION", "TOOL", "RETRIEVAL"]}},
                    {"term": {"payload.attr.release_ring": params["release_ring"]}},
                    {"term": {"payload.attr.customer_tier": params["customer_tier"]}},
                    {"term": {"payload.attr.traffic_cluster": params["traffic_cluster"]}},
                ]
            }
        },
        "sort": [
            {"event_time": {"order": "desc"}},
            {"trace_id": {"order": "desc"}},
            {"observation_id": {"order": "desc"}},
        ],
        "_source": ["event_time", "trace_id", "observation_id", "type", "status", "payload"],
    }


def q17_body(params: Dict[str, str]) -> Dict[str, Any]:
    return {
        "size": 100,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"tenant": params["tenant"]}},
                    {"term": {"payload.attr.request_key": params["request_key"]}},
                    {"term": {"payload.attr.workflow_variant": params["workflow_variant"]}},
                ]
            }
        },
        "sort": [
            {"seq_no": {"order": "asc"}},
            {"observation_id": {"order": "asc"}},
        ],
        "_source": ["trace_id", "observation_id", "seq_no", "type", "status", "payload"],
    }


def q18_body() -> Dict[str, Any]:
    return {
        "size": 0,
        "query": {"terms": {"type": ["GENERATION", "REASONING", "TOOL"]}},
        "aggs": {
            "prompt_template_version": {
                "terms": {"field": "payload.attr.prompt_template_version", "size": 20},
                "aggs": {
                    "traces": {"cardinality": {"field": "trace_id"}},
                    "avg_latency_ms": {"avg": {"field": "latency_ms"}},
                    "total_cost": {"sum": {"field": "total_cost"}},
                },
            }
        },
    }


def q19_body() -> Dict[str, Any]:
    return {
        "size": 0,
        "query": {
            "bool": {
                "filter": [{"terms": {"type": ["GENERATION", "TOOL", "RETRIEVAL", "EVENT"]}}],
                "must": [
                    {
                        "multi_match": {
                            "query": "error timeout retry",
                            "fields": TEXT_FIELDS,
                            "operator": "or",
                        }
                    }
                ],
            }
        },
        "aggs": {
            "deployment_channel": {
                "terms": {"field": "payload.attr.deployment_channel", "size": 10},
                "aggs": {
                    "release_ring": {
                        "terms": {"field": "payload.attr.release_ring", "size": 10},
                        "aggs": {
                            "incident_traces": {"cardinality": {"field": "trace_id"}},
                            "avg_latency_ms": {"avg": {"field": "latency_ms"}},
                        },
                    }
                },
            }
        },
    }


def q20_body() -> Dict[str, Any]:
    return {
        "size": 0,
        "query": {"terms": {"type": ["GENERATION", "TOOL", "RETRIEVAL", "REASONING"]}},
        "aggs": {
            "workflow_variant": {
                "terms": {"field": "payload.attr.workflow_variant", "size": 20},
                "aggs": {
                    "policy_pack": {
                        "terms": {"field": "payload.attr.policy_pack", "size": 10},
                        "aggs": {
                            "tenants": {"cardinality": {"field": "tenant"}},
                            "avg_latency_ms": {"avg": {"field": "latency_ms"}},
                            "total_cost": {"sum": {"field": "total_cost"}},
                        },
                    }
                },
            }
        },
    }


def query_rows(query_id: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if query_id == "Q01":
        return [{field: extract_source(hit).get(field) for field in QUERY_FIELDS["Q01"]} for hit in payload["hits"]["hits"]]
    if query_id == "Q02":
        rows = bucket_rows(
            payload["aggregations"]["trace_id"]["buckets"],
            lambda bucket: {
                "trace_id": bucket["key"],
                "started_at": bucket["started_at"].get("value_as_string"),
                "observation_count": bucket["doc_count"],
                "failure_count": bucket["failure_count"]["doc_count"],
                "total_cost": numeric_value(bucket["total_cost"]["value"]),
                "total_latency_ms": numeric_value(bucket["total_latency_ms"]["value"]),
            },
        )
        return sorted(
            rows,
            key=lambda row: (-stable_num(row["total_cost"]), -stable_num(row["total_latency_ms"]), stable_text(row["trace_id"])),
        )[:50]
    if query_id == "Q03":
        return [{field: extract_source(hit).get(field) for field in QUERY_FIELDS["Q03"]} for hit in payload["hits"]["hits"]]
    if query_id == "Q04":
        hits = [extract_source(hit) for hit in payload["hits"]["hits"]]
        by_observation_id = {row.get("observation_id"): row for row in hits}
        rows = []
        for row in hits:
            parent = by_observation_id.get(row.get("parent_observation_id"))
            rows.append(
                {
                    "trace_id": row.get("trace_id"),
                    "seq_no": row.get("seq_no"),
                    "observation_id": row.get("observation_id"),
                    "parent_observation_id": row.get("parent_observation_id"),
                    "parent_type": parent.get("type") if parent else None,
                    "child_type": row.get("type"),
                    "status": row.get("status"),
                    "tool_name": row.get("tool_name"),
                }
            )
        return rows
    if query_id == "Q05":
        rows = []
        for hit in payload["hits"]["hits"]:
            source = extract_source(hit)
            rows.append(
                {
                    "event_time": source.get("event_time"),
                    "trace_id": source.get("trace_id"),
                    "observation_id": source.get("observation_id"),
                    "tool_name": source.get("tool_name"),
                    "latency_ms": source.get("latency_ms"),
                    "text_score": text_score(source, Q05_TEXT_SCORE_TOKENS),
                    "payload": source.get("payload"),
                }
            )
        rows = [row for row in rows if row["text_score"] >= len(Q05_TEXT_SCORE_TOKENS)]
        return sorted(rows, key=lambda row: (row["text_score"], row["latency_ms"], row["event_time"]), reverse=True)[:50]
    if query_id == "Q06":
        rows: List[Dict[str, Any]] = []
        for type_bucket in payload["aggregations"]["type"]["buckets"]:
            for model_bucket in type_bucket["model"]["buckets"]:
                rows.append(
                    {
                        "type": type_bucket["key"],
                        "model": model_bucket["key"],
                        "observations": model_bucket["doc_count"],
                        "input_tokens": numeric_value(model_bucket["input_tokens"]["value"]),
                        "output_tokens": numeric_value(model_bucket["output_tokens"]["value"]),
                        "total_cost": numeric_value(model_bucket["total_cost"]["value"]),
                        "avg_latency_ms": numeric_value(model_bucket["avg_latency_ms"]["value"]),
                    }
                )
        return sorted(
            rows,
            key=lambda row: (
                -stable_num(row["total_cost"]),
                -stable_num(row["avg_latency_ms"]),
                -stable_num(row["observations"]),
                -stable_num(row["input_tokens"]),
                -stable_num(row["output_tokens"]),
                stable_text(row["type"]),
                stable_text(row["model"]),
            ),
        )[:50]
    if query_id == "Q07":
        return [{field: extract_source(hit).get(field) for field in QUERY_FIELDS["Q07"]} for hit in payload["hits"]["hits"]]
    if query_id == "Q08":
        rows = []
        for hit in payload["hits"]["hits"]:
            source = extract_source(hit)
            rows.append(
                {
                    "event_time": source.get("event_time"),
                    "trace_id": source.get("trace_id"),
                    "observation_id": source.get("observation_id"),
                    "type": source.get("type"),
                    "status": source.get("status"),
                    "input": source.get("input"),
                    "output": source.get("output"),
                    "phrase_match": phrase_match(source),
                    "text_score": text_score(source, Q08_TEXT_SCORE_TOKENS),
                }
            )
        rows = [row for row in rows if row["phrase_match"] and row["text_score"] >= len(Q08_TEXT_SCORE_TOKENS)]
        return sorted(
            rows,
            key=lambda row: (
                row["phrase_match"],
                row["text_score"],
                stable_text(row["event_time"]),
                stable_text(row["trace_id"]),
                stable_text(row["observation_id"]),
            ),
            reverse=True,
        )[:50]
    if query_id == "Q09":
        rows: List[Dict[str, Any]] = []
        for tool_bucket in payload["aggregations"]["tool_name"]["buckets"]:
            for status_bucket in tool_bucket["status"]["buckets"]:
                rows.append(
                    {
                        "tool_name": tool_bucket["key"],
                        "status": status_bucket["key"],
                        "observations": status_bucket["doc_count"],
                        "avg_latency_ms": numeric_value(status_bucket["avg_latency_ms"]["value"]),
                    }
                )
        return sorted(
            rows,
            key=lambda row: (-stable_num(row["observations"]), -stable_num(row["avg_latency_ms"]), stable_text(row["tool_name"]), stable_text(row["status"])),
        )[:50]
    if query_id == "Q10":
        rows: List[Dict[str, Any]] = []
        for stop_reason_bucket in payload["aggregations"]["stop_reason"]["buckets"]:
            for cache_hit_bucket in stop_reason_bucket["cache_hit"]["buckets"]:
                cache_value = cache_hit_bucket.get("key_as_string")
                if cache_value in (True, False):
                    cache_value = "true" if cache_value else "false"
                elif cache_value in ("true", "false"):
                    cache_value = cache_value
                else:
                    cache_value = "true" if bool(cache_hit_bucket.get("key")) else "false"
                rows.append(
                    {
                        "stop_reason": stop_reason_bucket["key"],
                        "cache_hit": cache_value,
                        "observations": cache_hit_bucket["doc_count"],
                        "avg_latency_ms": numeric_value(cache_hit_bucket["avg_latency_ms"]["value"]),
                    }
                )
        return sorted(
            rows,
            key=lambda row: (-stable_num(row["observations"]), -stable_num(row["avg_latency_ms"]), stable_text(row["stop_reason"]), stable_text(row["cache_hit"])),
        )[:50]
    if query_id == "Q11":
        rows = []
        for hit in payload["hits"]["hits"]:
            source = extract_source(hit)
            rows.append(
                {
                    "event_time": source.get("event_time"),
                    "trace_id": source.get("trace_id"),
                    "observation_id": source.get("observation_id"),
                    "type": source.get("type"),
                    "status": source.get("status"),
                    "tool_name": source.get("tool_name"),
                    "latency_ms": source.get("latency_ms"),
                    "phrase_match": phrase_match(source),
                    "text_score": text_score(source, Q08_TEXT_SCORE_TOKENS),
                }
            )
        rows = [row for row in rows if row["phrase_match"] and row["text_score"] >= len(Q08_TEXT_SCORE_TOKENS)]
        return sorted(
            rows,
            key=lambda row: (
                -stable_num(row["phrase_match"]),
                -stable_num(row["text_score"]),
                -stable_num(row["latency_ms"]),
                stable_text(row["event_time"]),
                stable_text(row["trace_id"]),
                stable_text(row["observation_id"]),
            ),
        )[:50]
    if query_id == "Q12":
        rows: List[Dict[str, Any]] = []
        for release_ring_bucket in payload["aggregations"]["release_ring"]["buckets"]:
            for customer_tier_bucket in release_ring_bucket["customer_tier"]["buckets"]:
                for retrieval_bucket in customer_tier_bucket["retrieval_strategy"]["buckets"]:
                    rows.append(
                        {
                            "release_ring": release_ring_bucket["key"],
                            "customer_tier": customer_tier_bucket["key"],
                            "retrieval_strategy": retrieval_bucket["key"],
                            "observations": retrieval_bucket["doc_count"],
                            "avg_latency_ms": numeric_value(retrieval_bucket["avg_latency_ms"]["value"]),
                            "total_cost": numeric_value(retrieval_bucket["total_cost"]["value"]),
                        }
                    )
        return sorted(
            rows,
            key=lambda row: (
                -stable_num(row["observations"]),
                -stable_num(row["total_cost"]),
                stable_text(row["release_ring"]),
                stable_text(row["customer_tier"]),
                stable_text(row["retrieval_strategy"]),
            ),
        )[:50]
    if query_id == "Q13":
        return [
            {
                "observations": payload["hits"]["total"]["value"],
                "traces": numeric_value(payload["aggregations"]["traces"]["value"]),
                "last_event_time": payload["aggregations"]["last_event_time"].get("value_as_string"),
            }
        ]
    if query_id == "Q14":
        return [
            {
                "event_time": source.get("event_time"),
                "trace_id": source.get("trace_id"),
                "observation_id": source.get("observation_id"),
                "type": source.get("type"),
                "status": source.get("status"),
                "tool_name": source.get("tool_name"),
            }
            for source in (extract_source(hit) for hit in payload["hits"]["hits"])
        ]
    if query_id == "Q15":
        return [
            {
                "event_time": source.get("event_time"),
                "trace_id": source.get("trace_id"),
                "observation_id": source.get("observation_id"),
                "type": source.get("type"),
                "status": source.get("status"),
                "tool_name": source.get("tool_name"),
                "latency_ms": source.get("latency_ms"),
            }
            for source in (extract_source(hit) for hit in payload["hits"]["hits"])
        ]
    if query_id == "Q16":
        return [
            {
                "event_time": source.get("event_time"),
                "trace_id": source.get("trace_id"),
                "observation_id": source.get("observation_id"),
                "type": source.get("type"),
                "status": source.get("status"),
                "release_ring": attr_value(source, "release_ring"),
                "customer_tier": attr_value(source, "customer_tier"),
                "traffic_cluster": attr_value(source, "traffic_cluster"),
            }
            for source in (extract_source(hit) for hit in payload["hits"]["hits"])
        ]
    if query_id == "Q17":
        return [
            {
                "trace_id": source.get("trace_id"),
                "observation_id": source.get("observation_id"),
                "seq_no": source.get("seq_no"),
                "type": source.get("type"),
                "status": source.get("status"),
                "request_key": attr_value(source, "request_key"),
                "workflow_variant": attr_value(source, "workflow_variant"),
            }
            for source in (extract_source(hit) for hit in payload["hits"]["hits"])
        ]
    if query_id == "Q18":
        rows = []
        for bucket in payload["aggregations"]["prompt_template_version"]["buckets"]:
            rows.append(
                {
                    "prompt_template_version": bucket["key"],
                    "observations": bucket["doc_count"],
                    "traces": numeric_value(bucket["traces"]["value"]),
                    "avg_latency_ms": numeric_value(bucket["avg_latency_ms"]["value"]),
                    "total_cost": numeric_value(bucket["total_cost"]["value"]),
                }
            )
        return sorted(
            rows,
            key=lambda row: (
                -stable_num(row["observations"]),
                -stable_num(row["total_cost"]),
                stable_text(row["prompt_template_version"]),
            ),
        )[:20]
    if query_id == "Q19":
        rows = []
        for channel_bucket in payload["aggregations"]["deployment_channel"]["buckets"]:
            for release_ring_bucket in channel_bucket["release_ring"]["buckets"]:
                rows.append(
                    {
                        "deployment_channel": channel_bucket["key"],
                        "release_ring": release_ring_bucket["key"],
                        "incident_observations": release_ring_bucket["doc_count"],
                        "incident_traces": numeric_value(release_ring_bucket["incident_traces"]["value"]),
                        "avg_latency_ms": numeric_value(release_ring_bucket["avg_latency_ms"]["value"]),
                    }
                )
        return sorted(
            rows,
            key=lambda row: (
                -stable_num(row["incident_observations"]),
                -stable_num(row["incident_traces"]),
                stable_text(row["deployment_channel"]),
                stable_text(row["release_ring"]),
            ),
        )[:20]
    if query_id == "Q20":
        rows = []
        for workflow_bucket in payload["aggregations"]["workflow_variant"]["buckets"]:
            for policy_bucket in workflow_bucket["policy_pack"]["buckets"]:
                rows.append(
                    {
                        "workflow_variant": workflow_bucket["key"],
                        "policy_pack": policy_bucket["key"],
                        "observations": policy_bucket["doc_count"],
                        "tenants": numeric_value(policy_bucket["tenants"]["value"]),
                        "avg_latency_ms": numeric_value(policy_bucket["avg_latency_ms"]["value"]),
                        "total_cost": numeric_value(policy_bucket["total_cost"]["value"]),
                    }
                )
        return sorted(
            rows,
            key=lambda row: (
                -stable_num(row["observations"]),
                -stable_num(row["total_cost"]),
                stable_text(row["workflow_variant"]),
                stable_text(row["policy_pack"]),
            ),
        )[:20]
    raise KeyError(f"Unsupported query_id {query_id}")


def build_query_body(query_id: str, params: Dict[str, str]) -> Dict[str, Any]:
    builders = {
        "Q01": lambda: q01_body(params),
        "Q02": lambda: q02_body(params),
        "Q03": lambda: q03_body(params),
        "Q04": lambda: q04_body(params),
        "Q05": lambda: q05_body(params),
        "Q06": q06_body,
        "Q07": q07_body,
        "Q08": lambda: q08_body(params),
        "Q09": q09_body,
        "Q10": q10_body,
        "Q11": lambda: q11_body(params),
        "Q12": q12_body,
        "Q13": lambda: q13_body(params),
        "Q14": lambda: q14_body(params),
        "Q15": lambda: q15_body(params),
        "Q16": lambda: q16_body(params),
        "Q17": lambda: q17_body(params),
        "Q18": q18_body,
        "Q19": q19_body,
        "Q20": q20_body,
    }
    return builders[query_id]()


def fetch_engine_version(endpoint: str) -> str:
    payload = json_request("GET", f"{endpoint}/", timeout=30)
    version = payload.get("version", {}).get("number", "unknown")
    distribution = str(payload.get("version", {}).get("distribution") or "").strip().lower()
    if distribution:
        return f"{distribution}-{version}"
    if search_engine_slug() == "opensearch":
        return f"opensearch-{version}"
    return f"elasticsearch-{version}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run observation-first search-engine benchmark queries.")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--out-file", type=Path, required=True)
    parser.add_argument("--result-file", type=Path, default=None)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--index", required=True)
    parser.add_argument("--storage-path", type=Path, required=True)
    args = parser.parse_args()

    root = args.root
    agentlogsbench_root = root / "agentlogsbench"
    manifest_path = Path(
        os.environ.get("AIBENCH_MANIFEST_PATH", str(bundled_small_data_dir(agentlogsbench_root) / "manifest.json"))
    )
    manifest = load_manifest(manifest_path)
    skip_contract_verification = env_flag("AIBENCH_SKIP_CONTRACT_VERIFICATION")
    dataset_tier = os.environ.get("AIBENCH_DATASET_TIER", "S")
    dataset_version = os.environ.get("AIBENCH_DATASET_VERSION", manifest["edition"])
    contracts = json.loads(query_contracts_path(agentlogsbench_root).read_text(encoding="utf-8"))["contracts"]
    edition_text = edition_path(agentlogsbench_root).read_text(encoding="utf-8")
    edition = json.loads(edition_text)
    engine_slug = search_engine_slug()
    adapter = json.loads(adapter_manifest_path(agentlogsbench_root, engine_slug).read_text(encoding="utf-8"))
    query_map = json.loads(adapter_query_map_path(agentlogsbench_root, engine_slug).read_text(encoding="utf-8"))
    timeout_seconds = int(edition["execution_protocol"]["timeout_seconds"])

    args.result_dir.mkdir(parents=True, exist_ok=True)
    args.out_file.parent.mkdir(parents=True, exist_ok=True)
    result_file = args.result_file or (args.result_dir / "result.json")
    result_file.parent.mkdir(parents=True, exist_ok=True)

    params = load_context_from_paths(manifest_observation_paths(manifest_path, manifest), manifest["replay_trace_id"])
    engine_version = fetch_engine_version(args.endpoint)

    query_results: List[Dict[str, Any]] = []
    log_lines: List[str] = []

    for query in load_query_definitions(agentlogsbench_root):
        query_id = query["id"]
        body = build_query_body(query_id, params)
        contract = contracts[query_id]
        assertion_keys = sorted(contract["assertions"].keys())
        compiled_fingerprint = sha256_text(json.dumps(body, sort_keys=True, ensure_ascii=False))
        try:
            _, _ = search(args.endpoint, args.index, body, timeout_seconds)
            runs: List[int] = []
            rows: List[Dict[str, Any]] = []
            last_payload: Dict[str, Any] = {}
            for _ in range(5):
                payload, elapsed_ms = search(args.endpoint, args.index, body, timeout_seconds)
                last_payload = payload
                runs.append(elapsed_ms)
                rows = query_rows(query_id, payload)

            rows = normalize_query_rows(rows)
            observed_fields = ordered_fields(query_id, rows)
            missing_fields, row_count_errors, result_fingerprint = verify_contract(contract, rows, observed_fields)
            if skip_contract_verification:
                row_count_errors = []
            fingerprint_errors: List[str] = []
            expected_result_fingerprint = contract.get("expected_result_fingerprints", {}).get("elastic")
            if (
                not skip_contract_verification
                and isinstance(expected_result_fingerprint, str)
                and result_fingerprint != expected_result_fingerprint
            ):
                fingerprint_errors.append(
                    f"result_fingerprint {result_fingerprint} != expected_result_fingerprint {expected_result_fingerprint}"
                )
            status = "incorrect" if missing_fields or row_count_errors or fingerprint_errors else "ok"
            error_text = ""
        except TimeoutError as exc:
            runs = [timeout_seconds * 1000] * 5
            rows = []
            observed_fields = QUERY_FIELDS[query_id]
            row_count_errors = []
            missing_fields = []
            result_fingerprint = ""
            fingerprint_errors = []
            status = "timeout"
            error_text = str(exc)
            last_payload = {"error": f"timeout after {timeout_seconds}s"}
        except urllib_error.URLError as exc:
            is_timeout = isinstance(exc.reason, TimeoutError)
            runs = [timeout_seconds * 1000] * 5
            rows = []
            observed_fields = QUERY_FIELDS[query_id]
            row_count_errors = []
            missing_fields = []
            result_fingerprint = ""
            fingerprint_errors = []
            status = "timeout" if is_timeout else "unsupported"
            error_text = str(exc)
            last_payload = {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            runs = [1, 1, 1, 1, 1]
            rows = []
            observed_fields = QUERY_FIELDS[query_id]
            row_count_errors = []
            missing_fields = []
            result_fingerprint = ""
            fingerprint_errors = []
            status = "unsupported"
            error_text = str(exc)
            last_payload = {"error": str(exc)}

        log_lines.append(render_query_log(query_id, body, rows or [last_payload], runs))
        if error_text:
            log_lines.append(f"ERROR: {error_text}\n\n")

        verification: Dict[str, Any] = {
            "contract_id": query_id,
            "fixture_dataset": contract["fixture_dataset"],
            "assertion_keys_checked": assertion_keys,
            "verification_mode": "benchmark_only" if skip_contract_verification else "fixture_contract",
            "observed_fields": observed_fields,
            "row_count": len(rows),
            "result_fingerprint": result_fingerprint,
            "canonical_sql_file": query["canonical_sql_file"],
            "engine_queries_file": "agentlogsbench/elastic/queries.json",
            "canonical_sql_section": query["canonical_sql_section"],
            "compiled_sql_fingerprint": compiled_fingerprint,
        }
        if missing_fields:
            verification["missing_fields"] = missing_fields
        if row_count_errors:
            verification["row_count_errors"] = row_count_errors
        if fingerprint_errors:
            verification["fingerprint_errors"] = fingerprint_errors

        query_results.append(
            {
                "query_id": query_id,
                "status": status,
                "latency_ms_runs": runs,
                "contract_verification": verification,
            }
        )

    args.out_file.write_text("".join(log_lines), encoding="utf-8")

    result = {
        "engine": "elastic",
        "edition": "2026.04-observability-v1",
        "dataset_tier": dataset_tier,
        "run_protocol": {
            "warmup_runs": 1,
            "measured_runs": 5,
            "timeout_seconds": timeout_seconds,
            "cache_policy": "disable_where_supported",
        },
        "run_metadata": {
            "dataset_version": dataset_version,
            "engine_version": engine_version,
            "config_fingerprint": sha256_text(edition_text),
            "index_config_fingerprint": sha256_text(json.dumps(adapter["declared_indexes"], sort_keys=True)),
            "query_adapter_version": str(query_map["adapter_version"]),
            "execution_mode": "runnable",
            "run_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
        "secondary_metrics": {
            "ingest_ms": 0,
            "index_build_ms": 0,
            "storage_bytes": storage_bytes(args.storage_path),
        },
        "query_results": query_results,
    }
    result_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
