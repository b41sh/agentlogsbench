from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable


SECTION_SEPARATOR = "-" * 120

QUERY_RESULT_COLUMNS: dict[str, list[str]] = {
    "Q01": ["event_time", "trace_id", "observation_id", "seq_no", "type", "status", "model", "tool_name", "latency_ms"],
    "Q02": ["trace_id", "started_at", "observation_count", "failure_count", "total_cost", "total_latency_ms"],
    "Q03": ["trace_id", "seq_no", "type", "status", "model", "tool_name"],
    "Q04": ["trace_id", "seq_no", "observation_id", "parent_observation_id", "type", "status", "tool_name"],
    "Q05": ["event_time", "trace_id", "observation_id", "tool_name", "latency_ms"],
    "Q06": ["type", "model", "observations", "input_tokens", "output_tokens", "total_cost", "avg_latency_ms"],
    "Q07": ["event_time", "trace_id", "observation_id", "type", "status"],
    "Q08": ["event_time", "trace_id", "observation_id", "type", "status"],
    "Q09": ["tool_name", "status", "observations", "avg_latency_ms"],
    "Q10": ["stop_reason", "cache_hit", "observations", "avg_latency_ms"],
    "Q11": ["event_time", "trace_id", "observation_id", "type", "status", "tool_name", "latency_ms"],
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

QUERY_RESULT_ALIASES: dict[str, dict[str, str]] = {
    "Q04": {"child_type": "type"},
}

SQL_RESULT_COLUMNS: dict[str, list[str]] = {
    "Q01": QUERY_RESULT_COLUMNS["Q01"],
    "Q02": QUERY_RESULT_COLUMNS["Q02"],
    "Q03": ["trace_id", "seq_no", "type", "status", "model", "tool_name", "input", "output"],
    "Q04": ["trace_id", "seq_no", "observation_id", "parent_observation_id", "parent_type", "child_type", "status", "tool_name"],
    "Q05": ["event_time", "trace_id", "observation_id", "tool_name", "latency_ms", "text_score", "payload"],
    "Q06": QUERY_RESULT_COLUMNS["Q06"],
    "Q07": ["event_time", "trace_id", "observation_id", "type", "status", "payload"],
    "Q08": ["event_time", "trace_id", "observation_id", "type", "status", "input", "output", "phrase_match", "text_score"],
    "Q09": QUERY_RESULT_COLUMNS["Q09"],
    "Q10": QUERY_RESULT_COLUMNS["Q10"],
    "Q11": ["event_time", "trace_id", "observation_id", "type", "status", "tool_name", "latency_ms", "phrase_match", "text_score"],
    "Q12": QUERY_RESULT_COLUMNS["Q12"],
    "Q13": QUERY_RESULT_COLUMNS["Q13"],
    "Q14": ["event_time", "trace_id", "observation_id", "type", "status", "tool_name", "output"],
    "Q15": QUERY_RESULT_COLUMNS["Q15"],
    "Q16": QUERY_RESULT_COLUMNS["Q16"],
    "Q17": QUERY_RESULT_COLUMNS["Q17"],
    "Q18": QUERY_RESULT_COLUMNS["Q18"],
    "Q19": QUERY_RESULT_COLUMNS["Q19"],
    "Q20": QUERY_RESULT_COLUMNS["Q20"],
}

SQL_CAPTURE_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "Q01": [(column, column) for column in QUERY_RESULT_COLUMNS["Q01"]],
    "Q02": [(column, column) for column in QUERY_RESULT_COLUMNS["Q02"]],
    "Q03": [(column, column) for column in QUERY_RESULT_COLUMNS["Q03"]],
    "Q04": [
        ("trace_id", "trace_id"),
        ("seq_no", "seq_no"),
        ("observation_id", "observation_id"),
        ("parent_observation_id", "parent_observation_id"),
        ("child_type", "type"),
        ("status", "status"),
        ("tool_name", "tool_name"),
    ],
    "Q05": [(column, column) for column in QUERY_RESULT_COLUMNS["Q05"]],
    "Q06": [(column, column) for column in QUERY_RESULT_COLUMNS["Q06"]],
    "Q07": [(column, column) for column in QUERY_RESULT_COLUMNS["Q07"]],
    "Q08": [(column, column) for column in QUERY_RESULT_COLUMNS["Q08"]],
    "Q09": [(column, column) for column in QUERY_RESULT_COLUMNS["Q09"]],
    "Q10": [(column, column) for column in QUERY_RESULT_COLUMNS["Q10"]],
    "Q11": [(column, column) for column in QUERY_RESULT_COLUMNS["Q11"]],
    "Q12": [(column, column) for column in QUERY_RESULT_COLUMNS["Q12"]],
    "Q13": [(column, column) for column in QUERY_RESULT_COLUMNS["Q13"]],
    "Q14": [(column, column) for column in QUERY_RESULT_COLUMNS["Q14"]],
    "Q15": [(column, column) for column in QUERY_RESULT_COLUMNS["Q15"]],
    "Q16": [(column, column) for column in QUERY_RESULT_COLUMNS["Q16"]],
    "Q17": [(column, column) for column in QUERY_RESULT_COLUMNS["Q17"]],
    "Q18": [(column, column) for column in QUERY_RESULT_COLUMNS["Q18"]],
    "Q19": [(column, column) for column in QUERY_RESULT_COLUMNS["Q19"]],
    "Q20": [(column, column) for column in QUERY_RESULT_COLUMNS["Q20"]],
}

ELASTIC_RESULT_LIMITS: dict[str, int] = {
    "Q01": 50,
    "Q02": 50,
    "Q05": 50,
    "Q06": 50,
    "Q07": 50,
    "Q08": 50,
    "Q09": 50,
    "Q10": 50,
    "Q11": 50,
    "Q12": 50,
    "Q13": 1,
    "Q14": 50,
    "Q15": 50,
    "Q16": 50,
    "Q17": 100,
    "Q18": 20,
    "Q19": 20,
    "Q20": 20,
}


def _stringify(value: Any) -> str:
    if value in (None, "", r"\N", "NULL", "None"):
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return format(value, ".15g")
    return str(value)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize_value(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_value(inner) for inner in value]
    if isinstance(value, Decimal):
        return _stringify(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if hasattr(value, "isoformat") and not isinstance(value, str):
        try:
            return value.isoformat()
        except TypeError:
            pass
    return _stringify(value)


def normalize_query_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {str(key): _normalize_value(value) for key, value in row.items()}
        for row in rows
    ]


def fingerprint_query_rows(rows: Iterable[dict[str, Any]]) -> str:
    payload = json.dumps(
        normalize_query_rows(rows),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def fingerprint_query_rows_excluding_fields(
    rows: Iterable[dict[str, Any]],
    excluded_fields: Iterable[str],
) -> str:
    excluded = set(excluded_fields)
    projected_rows = [
        {key: value for key, value in row.items() if key not in excluded}
        for row in normalize_query_rows(rows)
    ]
    payload = json.dumps(
        projected_rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _project_rows(query_id: str, columns: Iterable[str], rows: Iterable[Iterable[Any]]) -> tuple[list[str], list[list[str]]]:
    aliases = QUERY_RESULT_ALIASES.get(query_id, {})
    normalized_columns = [aliases.get(column, column) for column in columns]
    target_columns = QUERY_RESULT_COLUMNS[query_id]
    index_by_name = {column: index for index, column in enumerate(normalized_columns)}
    projected_rows: list[list[str]] = []
    for row in rows:
        row_values = list(row)
        projected_rows.append([_stringify(row_values[index_by_name[column]]) for column in target_columns])
    return target_columns, projected_rows


def parse_sql_result_text(query_id: str, text: str, *, with_header: bool) -> tuple[list[str], list[list[str]]]:
    reader = csv.reader(io.StringIO(text), delimiter="\t")
    rows = [row for row in reader if row]
    if with_header:
        if not rows:
            return QUERY_RESULT_COLUMNS[query_id], []
        columns = rows[0]
        data_rows = rows[1:]
    else:
        columns = SQL_RESULT_COLUMNS[query_id]
        data_rows = rows
    return _project_rows(query_id, columns, data_rows)


def _sort_string(value: Any) -> tuple[int, str]:
    text = _stringify(value)
    return (1, "") if text == "null" else (0, text)


def _sort_float_desc(value: Any) -> float:
    if value is None:
        return float("inf")
    return -float(value)


def _sort_int_desc(value: Any) -> int:
    if value is None:
        return 0
    return -int(value)


def _elastic_hits(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [hit.get("_source", {}) for hit in payload.get("hits", {}).get("hits", [])]


def _payload_attr(source: dict[str, Any], key: str) -> Any:
    payload = source.get("payload", {})
    if not isinstance(payload, dict):
        return None
    attr = payload.get("attr", {})
    if not isinstance(attr, dict):
        return None
    return attr.get(key)


def _extract_elastic_rows(query_id: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    if query_id in {"Q01", "Q03", "Q04", "Q05", "Q07", "Q08", "Q11"}:
        return _elastic_hits(payload)
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
            for source in _elastic_hits(payload)
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
            for source in _elastic_hits(payload)
        ]
    if query_id == "Q16":
        return [
            {
                "event_time": source.get("event_time"),
                "trace_id": source.get("trace_id"),
                "observation_id": source.get("observation_id"),
                "type": source.get("type"),
                "status": source.get("status"),
                "release_ring": _payload_attr(source, "release_ring"),
                "customer_tier": _payload_attr(source, "customer_tier"),
                "traffic_cluster": _payload_attr(source, "traffic_cluster"),
            }
            for source in _elastic_hits(payload)
        ]
    if query_id == "Q17":
        return [
            {
                "trace_id": source.get("trace_id"),
                "observation_id": source.get("observation_id"),
                "seq_no": source.get("seq_no"),
                "type": source.get("type"),
                "status": source.get("status"),
                "request_key": _payload_attr(source, "request_key"),
                "workflow_variant": _payload_attr(source, "workflow_variant"),
            }
            for source in _elastic_hits(payload)
        ]

    aggs = payload.get("aggregations", {})
    rows: list[dict[str, Any]] = []

    if query_id == "Q02":
        for bucket in aggs.get("trace_id", {}).get("buckets", []):
            rows.append(
                {
                    "trace_id": bucket.get("key"),
                    "started_at": bucket.get("started_at", {}).get("value_as_string"),
                    "observation_count": bucket.get("doc_count"),
                    "failure_count": bucket.get("failure_count", {}).get("doc_count"),
                    "total_cost": bucket.get("total_cost", {}).get("value"),
                    "total_latency_ms": bucket.get("total_latency_ms", {}).get("value"),
                }
            )
        rows.sort(
            key=lambda row: (
                _sort_float_desc(row.get("total_cost")),
                _sort_float_desc(row.get("total_latency_ms")),
                _sort_string(row.get("trace_id")),
            )
        )
        return rows

    if query_id == "Q13":
        return [
            {
                "observations": payload.get("hits", {}).get("total", {}).get("value", 0),
                "traces": aggs.get("traces", {}).get("value"),
                "last_event_time": aggs.get("last_event_time", {}).get("value_as_string"),
            }
        ]

    if query_id == "Q06":
        for type_bucket in aggs.get("type", {}).get("buckets", []):
            for model_bucket in type_bucket.get("model", {}).get("buckets", []):
                rows.append(
                    {
                        "type": type_bucket.get("key"),
                        "model": model_bucket.get("key"),
                        "observations": model_bucket.get("doc_count"),
                        "input_tokens": model_bucket.get("input_tokens", {}).get("value"),
                        "output_tokens": model_bucket.get("output_tokens", {}).get("value"),
                        "total_cost": model_bucket.get("total_cost", {}).get("value"),
                        "avg_latency_ms": model_bucket.get("avg_latency_ms", {}).get("value"),
                    }
                )
        rows.sort(
            key=lambda row: (
                _sort_float_desc(row.get("total_cost")),
                _sort_float_desc(row.get("avg_latency_ms")),
                _sort_int_desc(row.get("observations")),
                _sort_float_desc(row.get("input_tokens")),
                _sort_float_desc(row.get("output_tokens")),
                _sort_string(row.get("type")),
                _sort_string(row.get("model")),
            )
        )
        return rows

    if query_id == "Q09":
        for tool_bucket in aggs.get("tool_name", {}).get("buckets", []):
            for status_bucket in tool_bucket.get("status", {}).get("buckets", []):
                rows.append(
                    {
                        "tool_name": tool_bucket.get("key"),
                        "status": status_bucket.get("key"),
                        "observations": status_bucket.get("doc_count"),
                        "avg_latency_ms": status_bucket.get("avg_latency_ms", {}).get("value"),
                    }
                )
        rows.sort(
            key=lambda row: (
                _sort_int_desc(row.get("observations")),
                _sort_float_desc(row.get("avg_latency_ms")),
                _sort_string(row.get("tool_name")),
                _sort_string(row.get("status")),
            )
        )
        return rows

    if query_id == "Q10":
        for stop_reason_bucket in aggs.get("stop_reason", {}).get("buckets", []):
            for cache_hit_bucket in stop_reason_bucket.get("cache_hit", {}).get("buckets", []):
                rows.append(
                    {
                        "stop_reason": stop_reason_bucket.get("key"),
                        "cache_hit": cache_hit_bucket.get("key_as_string", _stringify(cache_hit_bucket.get("key"))),
                        "observations": cache_hit_bucket.get("doc_count"),
                        "avg_latency_ms": cache_hit_bucket.get("avg_latency_ms", {}).get("value"),
                    }
                )
        rows.sort(
            key=lambda row: (
                _sort_int_desc(row.get("observations")),
                _sort_float_desc(row.get("avg_latency_ms")),
                _sort_string(row.get("stop_reason")),
                _sort_string(row.get("cache_hit")),
            )
        )
        return rows

    if query_id == "Q12":
        for release_ring_bucket in aggs.get("release_ring", {}).get("buckets", []):
            for customer_tier_bucket in release_ring_bucket.get("customer_tier", {}).get("buckets", []):
                for retrieval_strategy_bucket in customer_tier_bucket.get("retrieval_strategy", {}).get("buckets", []):
                    rows.append(
                        {
                            "release_ring": release_ring_bucket.get("key"),
                            "customer_tier": customer_tier_bucket.get("key"),
                            "retrieval_strategy": retrieval_strategy_bucket.get("key"),
                            "observations": retrieval_strategy_bucket.get("doc_count"),
                            "avg_latency_ms": retrieval_strategy_bucket.get("avg_latency_ms", {}).get("value"),
                            "total_cost": retrieval_strategy_bucket.get("total_cost", {}).get("value"),
                        }
                    )
        rows.sort(
            key=lambda row: (
                _sort_int_desc(row.get("observations")),
                _sort_float_desc(row.get("total_cost")),
                _sort_string(row.get("release_ring")),
                _sort_string(row.get("customer_tier")),
                _sort_string(row.get("retrieval_strategy")),
            )
            )
        return rows

    if query_id == "Q18":
        for bucket in aggs.get("prompt_template_version", {}).get("buckets", []):
            rows.append(
                {
                    "prompt_template_version": bucket.get("key"),
                    "observations": bucket.get("doc_count"),
                    "traces": bucket.get("traces", {}).get("value"),
                    "avg_latency_ms": bucket.get("avg_latency_ms", {}).get("value"),
                    "total_cost": bucket.get("total_cost", {}).get("value"),
                }
            )
        rows.sort(
            key=lambda row: (
                _sort_int_desc(row.get("observations")),
                _sort_float_desc(row.get("total_cost")),
                _sort_string(row.get("prompt_template_version")),
            )
        )
        return rows

    if query_id == "Q19":
        for channel_bucket in aggs.get("deployment_channel", {}).get("buckets", []):
            for release_ring_bucket in channel_bucket.get("release_ring", {}).get("buckets", []):
                rows.append(
                    {
                        "deployment_channel": channel_bucket.get("key"),
                        "release_ring": release_ring_bucket.get("key"),
                        "incident_observations": release_ring_bucket.get("doc_count"),
                        "incident_traces": release_ring_bucket.get("incident_traces", {}).get("value"),
                        "avg_latency_ms": release_ring_bucket.get("avg_latency_ms", {}).get("value"),
                    }
                )
        rows.sort(
            key=lambda row: (
                _sort_int_desc(row.get("incident_observations")),
                _sort_float_desc(row.get("incident_traces")),
                _sort_string(row.get("deployment_channel")),
                _sort_string(row.get("release_ring")),
            )
        )
        return rows

    if query_id == "Q20":
        for workflow_bucket in aggs.get("workflow_variant", {}).get("buckets", []):
            for policy_bucket in workflow_bucket.get("policy_pack", {}).get("buckets", []):
                rows.append(
                    {
                        "workflow_variant": workflow_bucket.get("key"),
                        "policy_pack": policy_bucket.get("key"),
                        "observations": policy_bucket.get("doc_count"),
                        "tenants": policy_bucket.get("tenants", {}).get("value"),
                        "avg_latency_ms": policy_bucket.get("avg_latency_ms", {}).get("value"),
                        "total_cost": policy_bucket.get("total_cost", {}).get("value"),
                    }
                )
        rows.sort(
            key=lambda row: (
                _sort_int_desc(row.get("observations")),
                _sort_float_desc(row.get("total_cost")),
                _sort_string(row.get("workflow_variant")),
                _sort_string(row.get("policy_pack")),
            )
        )
        return rows

    raise KeyError(f"Unsupported Elasticsearch query id: {query_id}")


def extract_elasticsearch_result(query_id: str, payload: dict[str, Any]) -> tuple[list[str], list[list[str]]]:
    rows = _extract_elastic_rows(query_id, payload)
    limit = ELASTIC_RESULT_LIMITS.get(query_id)
    if limit is not None:
        rows = rows[:limit]
    target_columns = QUERY_RESULT_COLUMNS[query_id]
    return target_columns, [[_stringify(row.get(column)) for column in target_columns] for row in rows]


def format_query_result_section(query_id: str, columns: list[str], rows: list[list[str]]) -> str:
    widths = [len(column) for column in columns]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    def render(values: list[str]) -> str:
        return " | ".join(value.ljust(widths[index]) for index, value in enumerate(values))

    lines = [
        SECTION_SEPARATOR,
        "",
        f"Result for query {query_id}:",
        "",
        render(columns),
        "",
        "-+-".join("-" * width for width in widths),
    ]
    for row in rows:
        lines.append(render(row))
    lines.extend(["", ""])
    return "\n".join(lines)


def render_elasticsearch_result_section(query_id: str, payload: dict[str, Any]) -> str:
    columns, rows = extract_elasticsearch_result(query_id, payload)
    return format_query_result_section(query_id, columns, rows)


def render_sql_result_section(query_id: str, text: str, *, with_header: bool) -> str:
    columns, rows = parse_sql_result_text(query_id, text, with_header=with_header)
    return format_query_result_section(query_id, columns, rows)


def build_sql_capture_query(query_id: str, inner_query: str) -> str:
    select_list = []
    for source_column, target_column in SQL_CAPTURE_COLUMNS[query_id]:
        if source_column == target_column:
            select_list.append(source_column)
        else:
            select_list.append(f"{source_column} AS {target_column}")
    return "SELECT " + ", ".join(select_list) + f"\nFROM (\n{inner_query}\n) AS _query_result"
