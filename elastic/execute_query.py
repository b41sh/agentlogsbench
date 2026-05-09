#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib import request

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentlogsbench.tooling.query_results import render_elasticsearch_result_section


def json_post(endpoint: str, index: str, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
    started = time.perf_counter()
    req = request.Request(
        f"{endpoint}/{index}/_search?request_cache=false",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with request.urlopen(req, timeout=300) as response:
        payload = json.loads(response.read().decode("utf-8"))
    elapsed_ms = max(1, int((time.perf_counter() - started) * 1000))
    return payload, elapsed_ms


def composite_distinct_counts(
    endpoint: str,
    index: str,
    query: dict[str, Any],
    sources: list[dict[str, Any]],
    group_fields: list[str],
) -> tuple[Counter[tuple[str, ...]], int]:
    counts: Counter[tuple[str, ...]] = Counter()
    elapsed_ms = 0
    after_key: dict[str, Any] | None = None

    while True:
        composite: dict[str, Any] = {"size": 10000, "sources": sources}
        if after_key:
            composite["after"] = after_key
        body = {
            "size": 0,
            "track_total_hits": False,
            "query": query,
            "aggs": {
                "distinct_rows": {
                    "composite": composite,
                }
            },
        }
        payload, page_ms = json_post(endpoint, index, body)
        elapsed_ms += page_ms
        buckets = payload.get("aggregations", {}).get("distinct_rows", {}).get("buckets", [])
        for bucket in buckets:
            key = bucket["key"]
            counts[tuple(str(key[field]) for field in group_fields)] += 1
        after_key = payload.get("aggregations", {}).get("distinct_rows", {}).get("after_key")
        if not after_key:
            return counts, elapsed_ms


def composite_buckets(
    endpoint: str,
    index: str,
    query: dict[str, Any],
    agg_name: str,
    sources: list[dict[str, Any]],
    sub_aggs: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    buckets: list[dict[str, Any]] = []
    elapsed_ms = 0
    after_key: dict[str, Any] | None = None

    while True:
        composite: dict[str, Any] = {"size": 1000, "sources": sources}
        if after_key:
            composite["after"] = after_key
        agg_body: dict[str, Any] = {"composite": composite}
        if sub_aggs:
            agg_body["aggs"] = sub_aggs
        body = {
            "size": 0,
            "track_total_hits": False,
            "query": query,
            "aggs": {
                agg_name: agg_body,
            },
        }
        payload, page_ms = json_post(endpoint, index, body)
        elapsed_ms += page_ms
        agg_payload = payload.get("aggregations", {}).get(agg_name, {})
        buckets.extend(agg_payload.get("buckets", []))
        after_key = agg_payload.get("after_key")
        if not after_key:
            return buckets, elapsed_ms


def exact_payload(query_id: str, endpoint: str, index: str, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
    query = body["query"]

    if query_id == "Q02":
        buckets, elapsed_ms = composite_buckets(
            endpoint,
            index,
            query,
            "trace_id",
            [{"trace_id": {"terms": {"field": "trace_id"}}}],
            {
                "started_at": {"min": {"field": "event_time", "format": "yyyy-MM-dd HH:mm:ss"}},
                "failure_count": {"filter": {"bool": {"must_not": [{"term": {"status": "ok"}}]}}},
                "total_cost": {"sum": {"field": "total_cost"}},
                "total_latency_ms": {"sum": {"field": "latency_ms"}},
            },
        )
        for bucket in buckets:
            bucket["key"] = str(bucket.get("key", {}).get("trace_id", ""))
        return {"aggregations": {"trace_id": {"buckets": buckets}}}, elapsed_ms

    payload, elapsed_ms = json_post(endpoint, index, body)

    if query_id == "Q13":
        counts, extra_ms = composite_distinct_counts(
            endpoint,
            index,
            query,
            [{"trace_id": {"terms": {"field": "trace_id"}}}],
            ["trace_id"],
        )
        payload.setdefault("aggregations", {})["traces"] = {"value": sum(counts.values())}
        return payload, elapsed_ms + extra_ms

    if query_id == "Q18":
        counts, extra_ms = composite_distinct_counts(
            endpoint,
            index,
            query,
            [
                {"prompt_template_version": {"terms": {"field": "payload.attr.prompt_template_version"}}},
                {"trace_id": {"terms": {"field": "trace_id"}}},
            ],
            ["prompt_template_version"],
        )
        for bucket in payload.get("aggregations", {}).get("prompt_template_version", {}).get("buckets", []):
            bucket["traces"] = {"value": counts.get((str(bucket["key"]),), 0)}
        return payload, elapsed_ms + extra_ms

    if query_id == "Q19":
        counts, extra_ms = composite_distinct_counts(
            endpoint,
            index,
            query,
            [
                {"deployment_channel": {"terms": {"field": "payload.attr.deployment_channel"}}},
                {"release_ring": {"terms": {"field": "payload.attr.release_ring"}}},
                {"trace_id": {"terms": {"field": "trace_id"}}},
            ],
            ["deployment_channel", "release_ring"],
        )
        for channel_bucket in payload.get("aggregations", {}).get("deployment_channel", {}).get("buckets", []):
            channel_key = str(channel_bucket["key"])
            for ring_bucket in channel_bucket.get("release_ring", {}).get("buckets", []):
                ring_key = str(ring_bucket["key"])
                ring_bucket["incident_traces"] = {"value": counts.get((channel_key, ring_key), 0)}
        return payload, elapsed_ms + extra_ms

    return payload, elapsed_ms


def needs_exact_render(query_id: str) -> bool:
    return query_id in {"Q13", "Q18", "Q19"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute a single Elasticsearch benchmark query.")
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--index", required=True)
    parser.add_argument("--item-b64", required=True)
    parser.add_argument("--mode", choices=["timed", "render"], required=True)
    args = parser.parse_args()

    item = json.loads(base64.b64decode(args.item_b64).decode("utf-8"))["item"]
    query_id = item["id"]
    if args.mode == "render" and needs_exact_render(query_id):
        payload, elapsed_ms = exact_payload(query_id, args.endpoint, args.index, item["body"])
    else:
        payload, elapsed_ms = json_post(args.endpoint, args.index, item["body"])

    if args.mode == "timed":
        print(f"Response time: {elapsed_ms / 1000:.3f} s")
        return 0

    print(render_elasticsearch_result_section(query_id, payload), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
