from __future__ import annotations

import copy
import json
import random
import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from statistics import median
from typing import Any, Callable, Dict, Iterable, List, Tuple


MODEL_WEIGHTS = [
    ("reasoning-large", 0.18),
    ("reasoning-medium", 0.15),
    ("general-large", 0.15),
    ("general-medium", 0.15),
    ("coder-large", 0.14),
    ("coder-medium", 0.09),
    ("search-lite", 0.08),
    ("count-token-lite", 0.06),
]

TASK_CATEGORY_WEIGHTS = [
    ("coding_devops", 0.28),
    ("research_search", 0.22),
    ("office_productivity", 0.18),
    ("automation_workflow", 0.15),
    ("data_analysis", 0.10),
    ("safety_compliance", 0.07),
]

ARCHETYPE_WEIGHTS = [
    ("simple_chat", 0.24),
    ("tool_lookup", 0.23),
    ("research_agent", 0.16),
    ("retry_after_429", 0.08),
    ("timeout_then_fallback", 0.07),
    ("guardrail_block", 0.04),
    ("large_context_replay", 0.18),
]

REQUEST_KIND_WEIGHTS = [
    ("interactive_generation", 0.42),
    ("tool_heavy_generation", 0.22),
    ("long_context_generation", 0.14),
    ("count_tokens", 0.12),
    ("error_retry_guardrail", 0.10),
]

LANGUAGE_WEIGHTS = [
    ("english", 0.42),
    ("chinese", 0.16),
    ("mixed", 0.24),
    ("code_log", 0.18),
]

ENVIRONMENT_WEIGHTS = [("prod", 0.84), ("staging", 0.11), ("dev", 0.05)]

TENANT_COUNT_SMALL = 18
APP_COUNT_SMALL = 24

DYNAMIC_CORE_FIELD_POOLS = {
    "release_ring": ["stable", "canary", "shadow"],
    "customer_tier": ["free", "pro", "business", "enterprise"],
    "region": ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"],
    "surface": ["chat_ui", "api", "workflow_runner"],
    "retrieval_strategy": ["keyword", "dense", "hybrid", "hybrid_rerank"],
    "prompt_template_version": ["pt_2026_03_2", "pt_2026_04_1", "pt_2026_04_2"],
    "workflow_variant": [
        "direct_answer",
        "tool_first",
        "retrieval_then_reason",
        "review_revise",
        "long_context_replay",
        "guardrail_escalation",
    ],
    "memory_mode": ["off", "session", "hybrid", "persistent"],
    "policy_pack": ["default", "latency_strict", "cost_guarded", "enterprise_safe"],
    "deployment_channel": ["default", "shadow", "customer_rollout"],
    "experiment_bucket": ["control", "exp_a", "exp_b", "exp_c"],
    "traffic_cluster": ["cluster_a", "cluster_b", "cluster_c", "cluster_d"],
}
DYNAMIC_OPTIONAL_FIELD_POOLS = {
    "tool_family": ["shell", "editor", "browser", "retrieval", "deploy", "analytics", "memory"],
    "budget_policy": ["balanced", "latency_first", "quality_first", "cost_capped"],
    "cache_policy": ["no_cache", "read_through", "write_back", "semantic_cache"],
    "reasoning_effort": ["low", "medium", "high"],
    "eval_suite": ["regression", "retrieval", "safety", "latency", "cost"],
    "document_locale": ["en-US", "en-GB", "zh-CN", "ja-JP", "de-DE"],
    "scheduler_lane": ["interactive", "batch", "canary", "backfill"],
    "reranker_name": ["bm25", "colbert", "cross_encoder_v2", "hybrid_ranker"],
}
DYNAMIC_LONG_TAIL_DIMENSIONS = {
    "workspace": ("slug", "region", "tier", "channel", "owner", "route"),
    "route": ("name", "family", "tier", "channel", "bucket", "owner"),
    "agent": ("profile", "family", "mode", "owner", "route", "bucket"),
    "memory": ("policy", "tier", "channel", "bucket", "scope", "owner"),
    "guardrail": ("policy", "tier", "channel", "bucket", "scope", "owner"),
    "retrieval": ("index", "corpus", "strategy", "family", "bucket", "owner"),
    "toolchain": ("id", "family", "mode", "route", "bucket", "owner"),
    "user": ("segment", "tier", "channel", "bucket", "region", "owner"),
    "dataset": ("tag", "version", "channel", "bucket", "family", "owner"),
    "integration": ("channel", "family", "tier", "bucket", "scope", "owner"),
    "session": ("tier", "region", "channel", "bucket", "mode", "owner"),
    "workflow": ("variant", "family", "mode", "stage", "bucket", "owner"),
    "planner": ("mode", "strategy", "stage", "bucket", "scope", "owner"),
    "experiment": ("bucket", "family", "tier", "channel", "scope", "owner"),
    "deployment": ("channel", "family", "tier", "bucket", "scope", "owner"),
    "eval": ("suite", "family", "tier", "bucket", "scope", "owner"),
    "prompt": ("version", "family", "tier", "bucket", "scope", "owner"),
    "cache": ("policy", "tier", "channel", "bucket", "scope", "owner"),
    "provider": ("route", "region", "tier", "channel", "bucket", "owner"),
    "model": ("family", "tier", "channel", "bucket", "scope", "owner"),
    "trace": ("route", "family", "tier", "channel", "bucket", "owner"),
    "runbook": ("slug", "version", "tier", "channel", "scope", "owner"),
    "incident": ("family", "tier", "channel", "bucket", "scope", "owner"),
    "document": ("locale", "family", "tier", "channel", "bucket", "owner"),
}
DYNAMIC_LONG_TAIL_KEYS = sorted(
    {f"{prefix}_{suffix}" for prefix, suffixes in DYNAMIC_LONG_TAIL_DIMENSIONS.items() for suffix in suffixes}
    | {
        "workspace_slug",
        "route_name",
        "agent_profile",
        "memory_policy",
        "guardrail_policy",
        "retrieval_index",
        "toolchain_id",
        "user_segment",
        "dataset_tag",
        "integration_channel",
        "session_tier",
        "workspace_region",
    }
)
DYNAMIC_LONG_TAIL_VALUES = [
    "assistant",
    "research",
    "safe-default",
    "latency",
    "quality",
    "regional",
    "global",
    "premium",
    "self-serve",
    "beta",
    "ga",
    "shadow",
    "interactive",
    "batch",
    "triage",
    "review",
    "runtime",
    "ops",
    "retrieval",
    "customer",
]
SYNTHETIC_TOOL_CATALOG = [
    {
        "name": "mcp__matrix__bash_exec",
        "description": "Execute a shell command and capture stdout, stderr, exit code, and timing.",
        "input_schema": {"type": "object", "properties": {"command": {"type": "string"}, "cwd": {"type": "string"}, "env": {"type": "object"}}},
    },
    {
        "name": "mcp__matrix__read_file",
        "description": "Read a workspace file with line-aware context for debugging and review.",
        "input_schema": {"type": "object", "properties": {"target": {"type": "string"}, "cwd": {"type": "string"}}},
    },
    {
        "name": "mcp__matrix__edit_file",
        "description": "Apply an edit to a workspace file and return a compact diff preview.",
        "input_schema": {"type": "object", "properties": {"target": {"type": "string"}, "patch": {"type": "string"}, "cwd": {"type": "string"}}},
    },
    {
        "name": "mcp__matrix__web_search",
        "description": "Search the web for supporting evidence, incidents, or product documentation.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "top_k": {"type": "integer"}}},
    },
    {
        "name": "mcp__matrix__vector_search",
        "description": "Search a retrieval index for semantically related chunks and citations.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "index": {"type": "string"}, "top_k": {"type": "integer"}}},
    },
    {
        "name": "mcp__matrix__fetch_runbook",
        "description": "Fetch the latest runbook or playbook section for an incident or workflow.",
        "input_schema": {"type": "object", "properties": {"target": {"type": "string"}, "version": {"type": "string"}}},
    },
    {
        "name": "mcp__matrix__browser_navigate",
        "description": "Navigate to a page and capture page timing plus DOM metadata.",
        "input_schema": {"type": "object", "properties": {"target": {"type": "string"}, "timeout_ms": {"type": "integer"}}},
    },
    {
        "name": "mcp__matrix__browser_get_dom",
        "description": "Fetch the DOM snapshot of the current browser page for extraction or QA.",
        "input_schema": {"type": "object", "properties": {"target": {"type": "string"}}},
    },
    {
        "name": "mcp__matrix__inspect_metrics",
        "description": "Query metrics or dashboards for latency, error rate, and cost anomalies.",
        "input_schema": {"type": "object", "properties": {"service": {"type": "string"}, "window": {"type": "string"}}},
    },
    {
        "name": "mcp__matrix__tail_logs",
        "description": "Tail structured service logs and extract correlated error events.",
        "input_schema": {"type": "object", "properties": {"service": {"type": "string"}, "since": {"type": "string"}}},
    },
    {
        "name": "mcp__matrix__query_warehouse",
        "description": "Run an analytics query against the warehouse and return tabular results.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "warehouse": {"type": "string"}}},
    },
    {
        "name": "mcp__matrix__github_search_code",
        "description": "Search repository code for traces, incident markers, or config changes.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "repo": {"type": "string"}}},
    },
    {
        "name": "mcp__matrix__deploy_service",
        "description": "Deploy a service revision and capture rollout status with structured metadata.",
        "input_schema": {"type": "object", "properties": {"service": {"type": "string"}, "revision": {"type": "string"}, "env": {"type": "object"}}},
    },
    {
        "name": "mcp__matrix__rerank_results",
        "description": "Rerank retrieved chunks before a final answer or incident summary.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "candidate_count": {"type": "integer"}}},
    },
    {
        "name": "mcp__matrix__memory_upsert",
        "description": "Persist a memory or summary artifact into long-term workspace memory.",
        "input_schema": {"type": "object", "properties": {"target": {"type": "string"}, "content": {"type": "string"}}},
    },
    {
        "name": "mcp__matrix__artifact_extract_pdf",
        "description": "Extract key fields from an artifact such as a PDF incident report or spec.",
        "input_schema": {"type": "object", "properties": {"target": {"type": "string"}}},
    },
    {
        "name": "mcp__matrix__eval_trace",
        "description": "Evaluate a trace or answer quality and emit rubric scores.",
        "input_schema": {"type": "object", "properties": {"trace_id": {"type": "string"}, "rubric": {"type": "string"}}},
    },
    {
        "name": "mcp__matrix__schedule_workflow",
        "description": "Schedule or replay a workflow execution with controlled parameters.",
        "input_schema": {"type": "object", "properties": {"target": {"type": "string"}, "schedule": {"type": "string"}}},
    },
]
TOOL_PREFERENCES_BY_CATEGORY = {
    "coding_devops": ("bash", "read_file", "edit_file", "github", "deploy", "tail_logs"),
    "research_search": ("search", "vector_search", "fetch_runbook", "browser", "rerank"),
    "office_productivity": ("browser", "read_file", "memory", "artifact", "schedule"),
    "automation_workflow": ("schedule", "deploy", "memory", "read_file", "edit_file"),
    "data_analysis": ("query_warehouse", "inspect_metrics", "vector_search", "eval"),
    "safety_compliance": ("fetch_runbook", "artifact", "eval", "search", "read_file"),
}
TOOL_PREFERENCES_BY_ARCHETYPE = {
    "simple_chat": ("read_file", "browser", "memory"),
    "tool_lookup": ("search", "vector_search", "browser", "fetch_runbook"),
    "research_agent": ("search", "vector_search", "rerank", "browser", "artifact"),
    "retry_after_429": ("tail_logs", "inspect_metrics", "deploy", "read_file"),
    "timeout_then_fallback": ("tail_logs", "inspect_metrics", "search", "browser"),
    "guardrail_block": ("fetch_runbook", "eval", "artifact", "read_file"),
    "large_context_replay": ("read_file", "vector_search", "query_warehouse", "memory"),
}
TOPIC_POOLS = {
    "coding_devops": ["deployment rollback", "incident timeline", "pipeline regression", "service hotfix"],
    "research_search": ["competitor brief", "retrieval audit", "customer research synthesis", "market scan"],
    "office_productivity": ["meeting recap", "project update draft", "support handoff", "status memo"],
    "automation_workflow": ["workflow replay", "scheduler drift", "job orchestration fix", "handoff automation"],
    "data_analysis": ["cost outlier review", "latency regression analysis", "warehouse anomaly", "forecast refresh"],
    "safety_compliance": ["policy review", "red-team incident", "guardrail escalation", "audit evidence pack"],
}
MLFLOW_SPAN_TYPE_BY_OBSERVATION = {
    "GENERATION": "LLM",
    "TOKEN_ESTIMATE": "CHAIN",
    "REASONING": "CHAIN",
    "TOOL": "TOOL",
    "RETRIEVAL": "RETRIEVER",
    "EVENT": "CHAIN",
    "GUARDRAIL": "CHAIN",
}
LANGFUSE_OBSERVATION_TYPE_BY_OBSERVATION = {
    "GENERATION": "generation",
    "TOKEN_ESTIMATE": "event",
    "REASONING": "span",
    "TOOL": "span",
    "RETRIEVAL": "span",
    "EVENT": "event",
    "GUARDRAIL": "event",
}
OTEL_OPERATION_BY_OBSERVATION = {
    "GENERATION": "chat",
    "TOKEN_ESTIMATE": "count_tokens",
    "REASONING": "agent.reason",
    "TOOL": "execute_tool",
    "RETRIEVAL": "retrieval",
    "EVENT": "emit_event",
    "GUARDRAIL": "guardrail",
}
PROVIDER_WEIGHTS = [
    ("anthropic", 0.24),
    ("openai", 0.24),
    ("azure_openai", 0.14),
    ("vertex_ai", 0.12),
    ("bedrock", 0.10),
    ("gateway", 0.16),
]
PROVIDER_BASE_URLS = {
    "anthropic": "https://api.anthropic.example",
    "openai": "https://api.openai.example",
    "azure_openai": "https://azure-openai.example",
    "vertex_ai": "https://vertex-ai.example",
    "bedrock": "https://bedrock.example",
    "gateway": "https://gateway.example",
}

POSITIVE_PHRASES = {
    "error": [
        "permission denied",
        "rate limit exceeded",
        "No space left on device",
        "context length exceeded",
        "timeout awaiting headers",
        "503 Service Unavailable",
    ],
    "business": [
        "selforigin",
        "engage",
        "memory injection",
        "build in public",
        "multilingual rollout",
    ],
    "safety": [
        "guardrail blocked",
        "policy_violation",
        "pii detected",
        "sandbox escape attempt",
    ],
}

NEGATIVE_PHRASES = {
    "error": [
        "permissions denied",
        "permission-denied",
        "rate limited",
        "context too long",
    ],
    "business": [
        "self-origin",
        "engagement",
        "memory injected",
    ],
    "safety": [
        "guardrail block",
        "policy violation",
    ],
}

REQUEST_HEADERS_ALLOWLIST = ("x-request-id", "anthropic-version", "content-type", "user-agent")
RESPONSE_HEADERS_ALLOWLIST = ("x-response-id", "content-type")
RETRIEVAL_TOOL_HINTS = (
    "search",
    "news",
    "twitter_get",
    "extract_",
    "stocks_",
    "images_list",
    "fetch_runbook",
    "browser_get",
    "vector_search",
    "rerank",
    "artifact",
)


@dataclass
class SeedMaterial:
    messages_template: Dict[str, Any]
    count_tokens_template: Dict[str, Any]
    tools: List[Dict[str, Any]]
    text_snippets: List[str]
    thinking_snippets: List[str]
    tool_result_snippets: List[str]
    count_token_snippets: List[str]
    request_headers: Dict[str, str]
    response_headers: Dict[str, str]
    system_prompt: str


@dataclass
class GeneratedDataset:
    requests: List[Dict[str, Any]]
    observations: List[Dict[str, Any]]
    summary: Dict[str, Any]
    accuracy_labels: Dict[str, Any]
    manifest: Dict[str, Any]


@dataclass
class GeneratedShard:
    summary: Dict[str, Any]
    accuracy_labels: Dict[str, Any]
    manifest: Dict[str, Any]


def dedupe_preserve_order(values: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def build_synthetic_snippet_pool(kind: str) -> List[str]:
    if kind == "thinking":
        actions = [
            "I should verify the current trace topology before deciding on a fix",
            "I need to compare the latest tool output against the retrieved evidence",
            "I should preserve the causal chain between the failing step and the retry path",
            "I need to separate transient runtime noise from the real customer-facing regression",
        ]
        evidence = [
            "the last stderr fragment",
            "the retrieval chunk ranking",
            "the latency spike around the fallback path",
            "the runbook guidance for this workflow",
        ]
        next_steps = [
            "then summarize the impact on the tenant-facing workflow",
            "before deciding whether to retry, reroute, or escalate",
            "so the final answer can cite the right operational evidence",
            "while keeping the response aligned with the latest observation state",
        ]
        return [
            f"{action}; I should cross-check {evidence_item} {next_step}."
            for action in actions
            for evidence_item in evidence
            for next_step in next_steps
        ]
    if kind == "text":
        openings = [
            "I found enough evidence to draft a grounded answer",
            "The latest trace is coherent enough to summarize",
            "The tool and retrieval chain now points to a consistent explanation",
            "I can answer this without dropping the operational context",
        ]
        bodies = [
            "The likely issue is a workflow mismatch between the requested action and the retrieved context.",
            "The failure pattern looks correlated with a recent rollout and a stale cache path.",
            "The result set is consistent with a retrieval miss followed by a fallback tool path.",
            "The current evidence suggests a customer-visible slowdown rather than silent data loss.",
        ]
        closes = [
            "I will keep the answer short, cite the highest-signal evidence, and note the remaining uncertainty.",
            "I will preserve the trace lineage, the relevant tool output, and the retry behavior in the summary.",
            "I will reference the strongest retrieval hits and call out the parts that still need verification.",
            "I will keep the next action operationally useful instead of repeating the raw log content.",
        ]
        return [f"{opening} {body} {close}" for opening in openings for body in bodies for close in closes]
    if kind == "tool_result":
        subjects = [
            "deploy worker",
            "browser extraction",
            "retrieval pipeline",
            "warehouse query",
            "runbook fetch",
            "metrics probe",
        ]
        outcomes = [
            "completed with a partial warning on the first attempt",
            "returned a narrow result set after reranking",
            "timed out once and recovered on retry",
            "finished successfully with a stale-cache annotation",
            "returned inconsistent metadata that needs reconciliation",
        ]
        details = [
            "stderr contained one correlated stack line and no fatal crash marker",
            "the structured payload included latency, row count, and region tags",
            "the response carried an incident identifier plus a compact evidence preview",
            "the tool emitted a retry budget update together with the final exit status",
        ]
        return [f"{subject} {outcome}; {detail}." for subject in subjects for outcome in outcomes for detail in details]
    if kind == "count_tokens":
        shapes = [
            "Estimate token usage for the latest multi-turn trace replay",
            "Count tokens for a retrieval-heavy prompt with tool output included",
            "Estimate prompt size after preserving the last incident summary",
            "Count tokens for a bilingual debugging conversation with citations",
        ]
        qualifiers = [
            "Include the latest tool stderr and the customer-facing answer draft.",
            "Preserve the evidence excerpts and the fallback notes.",
            "Keep the runbook citations, but strip redundant boilerplate.",
            "Retain the final retry summary and the highest-signal metrics.",
        ]
        return [f"{shape} {qualifier}" for shape in shapes for qualifier in qualifiers]
    return []


def merge_tool_catalog(seed_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    catalog: Dict[str, Dict[str, Any]] = {}
    for tool in seed_tools + SYNTHETIC_TOOL_CATALOG:
        name = str(tool.get("name", "")).strip()
        if name:
            catalog[name] = copy.deepcopy(tool)
    return list(catalog.values())


def choose_provider_for_call(rng: random.Random, request_path: str, model: str) -> str:
    if request_path == "/v1/messages/count_tokens":
        return rng.choice(["gateway", "openai", "anthropic"])
    if model.startswith("reasoning"):
        return rng.choice(["anthropic", "openai", "gateway"])
    if model.startswith("coder"):
        return rng.choice(["openai", "azure_openai", "gateway"])
    return weighted_choice(rng, PROVIDER_WEIGHTS)


def weighted_choice(rng: random.Random, items: List[Tuple[str, float]]) -> str:
    total = sum(weight for _, weight in items)
    cut = rng.random() * total
    acc = 0.0
    for value, weight in items:
        acc += weight
        if acc >= cut:
            return value
    return items[-1][0]


def deterministic_uuid(prefix: str, idx: int) -> str:
    return f"{prefix}_{idx:06d}_{uuid.uuid5(uuid.NAMESPACE_DNS, f'{prefix}-{idx}').hex[:8]}"


def observation_uuid(trace_id: str, seq_no: int) -> str:
    token = uuid.uuid5(uuid.NAMESPACE_DNS, f"obs-{trace_id}-{seq_no}").hex[:8]
    return f"obs_{trace_id}_{seq_no:06d}_{token}"


def shift_event_time(timestamp: str, seconds: int) -> str:
    base = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
    return (base + timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S")


def make_long_tail_pool(prefix: str, count: int) -> List[str]:
    return [f"{prefix}_{i:03d}" for i in range(1, count + 1)]


def make_long_tail_weights(count: int) -> List[float]:
    return [1.0 / (idx ** 1.1) for idx in range(1, count + 1)]


def stable_seed_int(*parts: Any) -> int:
    token = "|".join(str(part) for part in parts)
    return int(uuid.uuid5(uuid.NAMESPACE_DNS, token).hex[:12], 16)


def workflow_variant_for(trace_archetype: str, request_kind: str) -> str:
    mapping = {
        "simple_chat": "direct_answer",
        "tool_lookup": "tool_first",
        "research_agent": "retrieval_then_reason",
        "retry_after_429": "retry_with_backoff",
        "timeout_then_fallback": "fallback_recovery",
        "guardrail_block": "guardrail_escalation",
        "large_context_replay": "long_context_replay",
    }
    if request_kind == "tool_heavy_generation":
        return "tool_first"
    if request_kind == "long_context_generation":
        return "long_context_replay"
    return mapping.get(trace_archetype, "review_revise")


def tool_family_from_name(tool_name: str | None) -> str:
    if not tool_name:
        return "none"
    lowered = tool_name.lower()
    family_map = {
        "browser": "browser",
        "search": "retrieval",
        "vector": "retrieval",
        "fetch": "retrieval",
        "rerank": "retrieval",
        "read": "editor",
        "edit": "editor",
        "bash": "shell",
        "deploy": "deploy",
        "log": "analytics",
        "metric": "analytics",
        "query": "analytics",
        "memory": "memory",
        "eval": "analytics",
        "artifact": "retrieval",
        "github": "editor",
    }
    for token, family in family_map.items():
        if token in lowered:
            return family
    return "utility"


def dynamic_value_for_key(field_name: str, raw: Dict[str, Any], base_seed: int, category_seed: int) -> Any:
    v = raw["v"]
    suffix = field_name.rsplit("_", 1)[-1]
    locale_map = {
        "english": "en-US",
        "chinese": "zh-CN",
        "mixed": "en-US",
        "code_log": "en-US",
    }
    route_values = ["answer", "retrieve", "tool", "retry", "fallback", "review"]
    owner_values = ["runtime", "search", "assistant", "safety", "platform", "growth"]
    stage_values = ["collect", "plan", "act", "observe", "recover", "summarize"]
    tier_values = ["bronze", "silver", "gold", "platinum"]
    channel_values = ["api", "chat_ui", "workflow_runner", "slack", "cli", "email"]
    corpus_values = ["prod_docs", "runbooks", "tickets", "analytics", "customer_notes", "specs"]

    if suffix == "slug":
        return f"{v['task_category'].replace('_', '-')}-{v['trace_archetype'].replace('_', '-')}"
    if suffix == "region":
        return DYNAMIC_CORE_FIELD_POOLS["region"][(base_seed + category_seed) % len(DYNAMIC_CORE_FIELD_POOLS["region"])]
    if suffix == "tier":
        return tier_values[(base_seed + category_seed) % len(tier_values)]
    if suffix == "channel":
        return channel_values[(base_seed + 2) % len(channel_values)]
    if suffix == "owner":
        return owner_values[(category_seed + 1) % len(owner_values)]
    if suffix == "route":
        return route_values[(base_seed + 3) % len(route_values)]
    if suffix == "name":
        return f"{v['task_category']}.{v['trace_archetype']}"
    if suffix == "family":
        return tool_family_from_name((v["request"]["body"].get("tools") or [{}])[0].get("name"))
    if suffix == "mode":
        return ["direct", "assistant", "review", "fallback", "planner"][(base_seed + 4) % 5]
    if suffix == "policy":
        return DYNAMIC_CORE_FIELD_POOLS["policy_pack"][(category_seed + 2) % len(DYNAMIC_CORE_FIELD_POOLS["policy_pack"])]
    if suffix == "scope":
        return ["trace", "session", "request", "tool", "retrieval", "tenant"][(base_seed + category_seed) % 6]
    if suffix == "strategy":
        return DYNAMIC_CORE_FIELD_POOLS["retrieval_strategy"][(base_seed + 1) % len(DYNAMIC_CORE_FIELD_POOLS["retrieval_strategy"])]
    if suffix == "bucket":
        return DYNAMIC_CORE_FIELD_POOLS["experiment_bucket"][(base_seed + 2) % len(DYNAMIC_CORE_FIELD_POOLS["experiment_bucket"])]
    if suffix == "stage":
        return stage_values[(base_seed + 5) % len(stage_values)]
    if suffix == "corpus":
        return corpus_values[(base_seed + category_seed) % len(corpus_values)]
    if suffix == "version":
        return f"2026.04.{1 + ((base_seed + category_seed) % 7)}"
    if suffix == "suite":
        return DYNAMIC_OPTIONAL_FIELD_POOLS["eval_suite"][(base_seed + 2) % len(DYNAMIC_OPTIONAL_FIELD_POOLS["eval_suite"])]
    if suffix == "locale":
        return locale_map.get(v["language_profile"], "en-US")
    if suffix == "id":
        return deterministic_uuid(field_name, (base_seed + category_seed) % 50000)
    if suffix == "variant":
        return workflow_variant_for(v["trace_archetype"], v["request_kind"])
    return DYNAMIC_LONG_TAIL_VALUES[(base_seed + category_seed) % len(DYNAMIC_LONG_TAIL_VALUES)]


def build_attr(raw: Dict[str, Any], observation_type: str, observation_id: str) -> Dict[str, Any]:
    v = raw["v"]
    base_seed = stable_seed_int(raw["request_id"], raw["session_id"], observation_type, observation_id)
    category_seed = stable_seed_int(v["task_category"], v["trace_archetype"])

    fields: Dict[str, Any] = {}
    tenant_num = int(v["tenant"].split("_")[-1])

    fields["release_ring"] = (
        ["stable", "canary", "shadow"][(base_seed + 3) % 3]
        if v["environment"] == "prod"
        else v["environment"]
    )
    fields["customer_tier"] = ["free", "pro", "business", "enterprise"][tenant_num % 4]
    fields["region"] = DYNAMIC_CORE_FIELD_POOLS["region"][(base_seed + category_seed) % len(DYNAMIC_CORE_FIELD_POOLS["region"])]
    fields["surface"] = (
        "workflow_runner"
        if v["trace_archetype"] in {"research_agent", "large_context_replay"}
        else ["chat_ui", "api", "workflow_runner"][(base_seed + 4) % 3]
    )
    fields["prompt_template_version"] = DYNAMIC_CORE_FIELD_POOLS["prompt_template_version"][
        (base_seed + 2) % len(DYNAMIC_CORE_FIELD_POOLS["prompt_template_version"])
    ]
    fields["retrieval_strategy"] = DYNAMIC_CORE_FIELD_POOLS["retrieval_strategy"][
        (base_seed + 1) % len(DYNAMIC_CORE_FIELD_POOLS["retrieval_strategy"])
    ]
    fields["workflow_variant"] = workflow_variant_for(v["trace_archetype"], v["request_kind"])
    fields["memory_mode"] = DYNAMIC_CORE_FIELD_POOLS["memory_mode"][
        (base_seed + 3) % len(DYNAMIC_CORE_FIELD_POOLS["memory_mode"])
    ]
    fields["policy_pack"] = DYNAMIC_CORE_FIELD_POOLS["policy_pack"][
        (category_seed + 1) % len(DYNAMIC_CORE_FIELD_POOLS["policy_pack"])
    ]
    fields["deployment_channel"] = DYNAMIC_CORE_FIELD_POOLS["deployment_channel"][
        (base_seed + 4) % len(DYNAMIC_CORE_FIELD_POOLS["deployment_channel"])
    ]
    fields["experiment_bucket"] = DYNAMIC_CORE_FIELD_POOLS["experiment_bucket"][
        (base_seed + 5) % len(DYNAMIC_CORE_FIELD_POOLS["experiment_bucket"])
    ]
    fields["traffic_cluster"] = DYNAMIC_CORE_FIELD_POOLS["traffic_cluster"][
        (category_seed + 2) % len(DYNAMIC_CORE_FIELD_POOLS["traffic_cluster"])
    ]

    optional_fields = list(DYNAMIC_OPTIONAL_FIELD_POOLS)
    if observation_type == "TOOL":
        preferred_optional = ["tool_family", "cache_policy", "scheduler_lane", "reasoning_effort"]
    elif observation_type == "RETRIEVAL":
        preferred_optional = ["tool_family", "reranker_name", "document_locale", "eval_suite"]
    elif observation_type == "REASONING":
        preferred_optional = ["reasoning_effort", "budget_policy", "cache_policy"]
    elif observation_type == "EVENT":
        preferred_optional = ["eval_suite", "scheduler_lane", "budget_policy"]
    else:
        preferred_optional = ["budget_policy", "cache_policy", "reasoning_effort", "eval_suite"]

    optional_order = preferred_optional + [field for field in optional_fields if field not in preferred_optional]
    optional_target = {
        "GENERATION": 4,
        "TOKEN_ESTIMATE": 4,
        "REASONING": 3,
        "TOOL": 4,
        "RETRIEVAL": 4,
        "EVENT": 3,
        "GUARDRAIL": 3,
    }.get(observation_type, 3)
    for offset in range(optional_target):
        field_name = optional_order[(base_seed + offset * 3) % len(optional_order)]
        pool = DYNAMIC_OPTIONAL_FIELD_POOLS[field_name]
        fields[field_name] = pool[(category_seed + offset * 5) % len(pool)]

    fields["request_key"] = raw["request_id"]

    extra_count = {
        "GENERATION": 8,
        "TOKEN_ESTIMATE": 7,
        "REASONING": 6,
        "TOOL": 8,
        "RETRIEVAL": 8,
        "EVENT": 5,
        "GUARDRAIL": 5,
    }.get(observation_type, 6)
    for offset in range(extra_count):
        key = DYNAMIC_LONG_TAIL_KEYS[(base_seed + offset * 5) % len(DYNAMIC_LONG_TAIL_KEYS)]
        value = dynamic_value_for_key(key, raw, base_seed + offset, category_seed + offset)
        fields[key] = value

    return fields


def build_resource_content(v: Dict[str, Any], attr: Dict[str, Any]) -> Dict[str, Any]:
    app_num = int(v["app"].split("_")[-1])
    service_version = f"2026.04.{1 + (app_num % 5)}"
    return {
        "service": {
            "name": v["app"],
            "namespace": v["tenant"],
            "version": service_version,
        },
        "deployment": {
            "environment": v["environment"],
        },
        "cloud": {
            "region": attr.get("region"),
        },
    }


def build_scope_content(observation_type: str) -> Dict[str, Any]:
    scope_name = {
        "GENERATION": "agentlogsbench.agent.generation",
        "REASONING": "agentlogsbench.agent.reasoning",
        "TOOL": "agentlogsbench.agent.tool",
        "RETRIEVAL": "agentlogsbench.agent.retrieval",
        "EVENT": "agentlogsbench.agent.event",
        "GUARDRAIL": "agentlogsbench.agent.guardrail",
        "TOKEN_ESTIMATE": "agentlogsbench.agent.tokens",
    }.get(observation_type, "agentlogsbench.agent.runtime")
    return {"name": scope_name, "version": "2026.04"}


def build_telemetry_content(
    raw: Dict[str, Any],
    observation_type: str,
    observation_id: str,
    attr: Dict[str, Any],
    status: str,
    tool_name: str | None = None,
    tool_call_id: str | None = None,
) -> Dict[str, Any]:
    v = raw["v"]
    request_body = v["request"]["body"]
    response_body = v["response"]["body"]
    usage = response_body.get("usage", {})
    otel_block: Dict[str, Any] = {
        "span_kind": "CLIENT" if observation_type in {"GENERATION", "TOKEN_ESTIMATE"} else "INTERNAL",
        "status_code": "ERROR" if status == "error" else "OK" if status == "ok" else "UNSET",
        "operation_name": OTEL_OPERATION_BY_OBSERVATION.get(observation_type, "runtime"),
    }
    if observation_type in {"GENERATION", "TOKEN_ESTIMATE"}:
        otel_block["gen_ai"] = {
            "provider_name": raw["source"],
            "request_model": raw["model"],
            "response_model": response_body.get("model", raw["model"]),
            "response_id": v["response"]["headers"].get("x-response-id"),
            "finish_reason": raw["stop_reason"],
            "input_tokens": usage.get("input_tokens", response_body.get("input_tokens", 0)),
            "output_tokens": usage.get("output_tokens", 0),
            "max_tokens": request_body.get("max_tokens"),
            "top_p": request_body.get("top_p"),
        }
    if tool_name:
        otel_block["tool"] = {
            "name": tool_name,
            "call_id": tool_call_id,
            "family": tool_family_from_name(tool_name),
        }
    return {
        "resource": build_resource_content(v, attr),
        "scope": build_scope_content(observation_type),
        "otel": otel_block,
        "langfuse": {
            "trace_id": v["trace_id"],
            "session_id": raw["session_id"],
            "observation_type": LANGFUSE_OBSERVATION_TYPE_BY_OBSERVATION.get(observation_type, "span"),
            "environment": v["environment"],
            "user_id": v["tenant"],
        },
        "mlflow": {
            "trace_id": v["trace_id"],
            "span_type": MLFLOW_SPAN_TYPE_BY_OBSERVATION.get(observation_type, "CHAIN"),
            "status": status,
            "request_id": raw["request_id"],
            "observation_id": observation_id,
        },
    }


def choose_hotspot_entity(
    rng: random.Random,
    pool: List[str],
    weights: List[float],
    hotspots: List[str],
    seen: set[str],
    floor_count: int,
) -> str:
    if len(seen) < min(floor_count, len(pool)):
        return pool[len(seen)]
    if hotspots and rng.random() < 0.72:
        return rng.choice(hotspots)
    return rng.choices(pool, weights=weights, k=1)[0]


def recursive_sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: recursive_sanitize(val) for key, val in value.items()}
    if isinstance(value, list):
        return [recursive_sanitize(item) for item in value]
    if isinstance(value, str):
        text = value
        needs_regex = (
            "/Users/" in text
            or "/home/" in text
            or "moltbook_sk_" in text
            or "sk_live_" in text
            or "req_" in text
            or "trace_" in text
            or "trace-" in text
            or ("." in text and any(char.isdigit() for char in text))
        )
        if needs_regex:
            text = re.sub(r"/Users/[^/\s]+", "/workspace/user", text)
            text = re.sub(r"/home/[^/\s]+", "/workspace/user", text)
            text = re.sub(r"moltbook_sk_[A-Za-z0-9_]+", "moltbook_sk_test_redacted", text)
            text = re.sub(r"sk_live_[A-Za-z0-9_]+", "sk_live_redacted", text)
            text = re.sub(r"req_[A-Za-z0-9_\-]+", "req_seed_redacted", text)
            text = re.sub(r"trace[_-][A-Za-z0-9_\-]+", "trace_seed_redacted", text)
            text = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "10.0.0.1", text)
        text = text.replace("same-element", "correlated")
        text = text.replace("helper tables", "secondary tables")
        text = text.replace("semantic cluster for search validation", "relevant context for investigation")
        text = text.replace("request replay", "execution replay")
        text = text.replace("tool_result", "execution output")
        text = text.replace("优先保留 trace 和 tool 关系", "优先保留最近的执行上下文")
        text = text.replace("错误：上下文过长，保留最近一次 tool_result 作为摘要。", "错误：上下文过长，保留最近一次执行输出作为摘要。")
        return text
    return value


def extract_strings(value: Any, out: List[str], min_len: int = 20) -> None:
    if isinstance(value, dict):
        for inner in value.values():
            extract_strings(inner, out, min_len=min_len)
        return
    if isinstance(value, list):
        for inner in value:
            extract_strings(inner, out, min_len=min_len)
        return
    if isinstance(value, str):
        text = recursive_sanitize(value).strip()
        if len(text) >= min_len:
            out.append(text)


def load_seed_material(seed_dir: Path) -> SeedMaterial:
    seed_paths = sorted(seed_dir.rglob("*.json"))
    if not seed_paths:
        raise FileNotFoundError(f"no seed json files found in {seed_dir}")
    parsed_seeds = [
        (str(path.relative_to(seed_dir)), recursive_sanitize(json.loads(path.read_text(encoding="utf-8"))))
        for path in seed_paths
    ]
    messages_seed_name, messages_template = next(
        (
            (name, payload)
            for name, payload in parsed_seeds
            if payload.get("request", {}).get("body", {}).get("system")
        ),
        parsed_seeds[0],
    )
    _, count_tokens_template = next(
        (
            (name, payload)
            for name, payload in parsed_seeds
            if "count_tokens" in json.dumps(payload.get("request", {}), ensure_ascii=False)
        ),
        parsed_seeds[-1],
    )

    text_snippets: List[str] = []
    thinking_snippets: List[str] = []
    tool_result_snippets: List[str] = []
    count_token_snippets: List[str] = []
    tools: List[Dict[str, Any]] = []

    for _, payload in parsed_seeds:
        request_body = payload.get("request", {}).get("body", {})
        for message in request_body.get("messages", []):
            content = message.get("content")
            if isinstance(content, list):
                for item in content:
                    item_type = item.get("type")
                    if item_type == "text":
                        extract_strings(item.get("text"), text_snippets)
                    elif item_type == "thinking":
                        extract_strings(item.get("thinking"), thinking_snippets)
                    elif item_type == "tool_result":
                        extract_strings(item.get("content"), tool_result_snippets)
            else:
                extract_strings(content, count_token_snippets, min_len=5)
        tools.extend(copy.deepcopy(request_body.get("tools", [])))

    request_headers = {
        key: str(messages_template["request"]["headers"][key])
        for key in messages_template["request"].get("headers", {})
        if key in REQUEST_HEADERS_ALLOWLIST
    }
    response_headers = {
        key: str(messages_template["response"]["headers"][key])
        for key in messages_template["response"].get("headers", {})
        if key in RESPONSE_HEADERS_ALLOWLIST
    }
    if "content-type" not in request_headers:
        request_headers["content-type"] = "application/json"
    if "content-type" not in response_headers:
        response_headers["content-type"] = "application/json"

    tools = merge_tool_catalog(tools)
    text_snippets = dedupe_preserve_order(text_snippets + build_synthetic_snippet_pool("text"))
    thinking_snippets = dedupe_preserve_order(thinking_snippets + build_synthetic_snippet_pool("thinking"))
    tool_result_snippets = dedupe_preserve_order(tool_result_snippets + build_synthetic_snippet_pool("tool_result"))
    count_token_snippets = dedupe_preserve_order(count_token_snippets + build_synthetic_snippet_pool("count_tokens"))
    return SeedMaterial(
        messages_template=messages_template,
        count_tokens_template=count_tokens_template,
        tools=tools,
        text_snippets=text_snippets or ["Continue the trace while keeping the recent context intact."],
        thinking_snippets=thinking_snippets or ["Need to preserve the tool context and retry history."],
        tool_result_snippets=tool_result_snippets or ["stderr: permission denied\nretry scheduled\npartial result preserved"],
        count_token_snippets=count_token_snippets or ["estimate tokens for current prompt"],
        request_headers=request_headers,
        response_headers=response_headers,
        system_prompt=str(
            messages_template["request"]["body"].get("system")
            or f"You are an agent assistant seeded from {messages_seed_name}."
        )[:4000],
    )


def choose_hour(rng: random.Random) -> int:
    buckets = [
        ((0, 6), 0.08),
        ((6, 9), 0.10),
        ((9, 12), 0.27),
        ((12, 14), 0.09),
        ((14, 18), 0.29),
        ((18, 22), 0.13),
        ((22, 24), 0.04),
    ]
    total = sum(weight for _, weight in buckets)
    cut = rng.random() * total
    acc = 0.0
    for (low, high), weight in buckets:
        acc += weight
        if acc >= cut:
            return rng.randint(low, high - 1)
    return 10


def plan_generation_counts(rng: random.Random, trace_target: int, generation_target: int) -> List[int]:
    if trace_target <= 0:
        raise ValueError("trace_target must be positive")
    if generation_target < trace_target:
        raise ValueError("generation_target must be >= trace_target")

    counts = [1 for _ in range(trace_target)]
    remaining = generation_target - trace_target
    while remaining > 0:
        idx = rng.randrange(trace_target)
        current = counts[idx]
        if current >= 6:
            continue
        weights = [(1, 0.74), (2, 0.16), (3, 0.05), (4, 0.03), (5, 0.02)]
        extra = int(weighted_choice(rng, [(str(v), w) for v, w in weights]))
        extra = min(extra, remaining, 6 - current)
        counts[idx] += extra
        remaining -= extra
    rng.shuffle(counts)
    return counts


def pick_body_bucket(rng: random.Random, request_path: str, huge_remaining: List[int]) -> Tuple[int, int, str]:
    if request_path == "/v1/messages/count_tokens":
        buckets = [
            (5_000, 20_000, "5KB-20KB", 0.72),
            (20_000, 50_000, "20KB-50KB", 0.25),
            (50_000, 100_000, "50KB-100KB", 0.03),
        ]
    else:
        if huge_remaining[0] > 0:
            huge_remaining[0] -= 1
            return 1_000_000, 2_000_000, "1MB-2MB"
        buckets = [
            (50_000, 120_000, "50KB-120KB", 0.38),
            (120_000, 200_000, "120KB-200KB", 0.26),
            (200_000, 350_000, "200KB-350KB", 0.20),
            (350_000, 500_000, "350KB-500KB", 0.16),
        ]
    total = sum(weight for _, _, _, weight in buckets)
    cut = rng.random() * total
    acc = 0.0
    for low, high, label, weight in buckets:
        acc += weight
        if acc >= cut:
            return low, high, label
    low, high, label, _ = buckets[-1]
    return low, high, label


def body_size_bytes(body: Dict[str, Any]) -> int:
    return len(json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def encoded_json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def append_message_with_size(messages: List[Dict[str, Any]], message_sizes: List[int], message: Dict[str, Any]) -> int:
    serialized_size = encoded_json_size(message)
    messages.append(message)
    message_sizes.append(serialized_size)
    return serialized_size + (1 if len(message_sizes) > 1 else 0)


def pop_message_with_size(messages: List[Dict[str, Any]], message_sizes: List[int]) -> int:
    messages.pop()
    serialized_size = message_sizes.pop()
    return serialized_size + (1 if message_sizes else 0)


def choose_text_profile(rng: random.Random) -> str:
    return weighted_choice(rng, LANGUAGE_WEIGHTS)


def seed_fragment(rng: random.Random, pool: List[str]) -> str:
    return rng.choice(pool).strip()


def make_context_block(seed: SeedMaterial, rng: random.Random, profile: str) -> str:
    if profile == "english":
        return seed_fragment(rng, seed.text_snippets)
    if profile == "chinese":
        return "继续保留上下文，不要重写之前的结论，优先保留最近的执行上下文。"
    if profile == "mixed":
        return seed_fragment(rng, seed.text_snippets)[:600] + "\n保持最近上下文完整，并保留关键错误细节。"
    return "path=/workspace/demo/service/api.py line=218\nstderr: permission denied\njson={\"status\":\"retry\"}"


def make_task_block(topic: str, category: str, app: str, tenant: str, archetype: str, intent: str, profile: str) -> str:
    if profile == "chinese":
        return (
            f"任务主题：{topic}；分类：{category}；应用：{app}；租户：{tenant}；"
            f"archetype={archetype}；意图：{intent}"
        )
    if profile == "mixed":
        return (
            f"Topic={topic}; category={category}; app={app}; tenant={tenant}; "
            f"Need: preserve recent execution context for {intent}"
        )
    if profile == "code_log":
        return (
            f"trace note: topic={topic}, category={category}, app={app}, tenant={tenant}, "
            f"intent={intent}, archetype={archetype}, "
            f"Need: keep nested tool outputs and recent execution context for {topic}/{intent}"
        )
    return (
        f"Continue the {topic} workflow for app={app} and tenant={tenant}. "
        f"Category={category}; intent={intent}; archetype={archetype}."
    )


def make_noisy_artifact(seed: SeedMaterial, rng: random.Random, request_id: str, trace_id: str, profile: str) -> str:
    request_suffix = request_id[-4:]
    trace_suffix = trace_id[-4:]
    cache_paths = [
        f"/workspace/output/cache_{request_suffix}.db",
        f"/workspace/runtime/session_{trace_suffix}.cache",
        f"/workspace/state/retrieval_{request_suffix}.sqlite",
        f"/workspace/artifacts/replay_{trace_suffix}.snapshot",
    ]
    retry_reasons = [
        "transient upstream failure",
        "stale cache metadata",
        "connector timeout",
        "retry budget depleted",
    ]
    stack_traces = [
        "RuntimeError -> TraceCompiler -> NestedFieldPlanner",
        "TimeoutError -> ToolRouter -> RetryBudget",
        "ValueError -> CitationAssembler -> ContextWindowSizer",
        "IOError -> ArtifactLoader -> SnapshotReader",
    ]
    line_builders: List[Callable[[], str]] = [
        lambda: f"corr_id={request_suffix}-{trace_suffix}",
        lambda: f"lineage_id={trace_suffix}-{request_suffix}",
        lambda: f"stderr: unable to open {rng.choice(cache_paths)}",
        lambda: (
            "json={"
            f"\"status\":\"{rng.choice(['retry', 'degraded', 'partial'])}\","
            f"\"reason\":\"{rng.choice(retry_reasons)}\","
            f"\"backoff_ms\":{rng.choice([800, 1200, 1800, 2400, 3200])},"
            f"\"attempt\":{rng.choice([1, 2, 3])},"
            f"\"corr\":\"{request_suffix}-{trace_suffix}\""
            "}"
        ),
        lambda: f"stack: {rng.choice(stack_traces)} corr={request_suffix}",
        lambda: (
            f"metrics: retrieval_hits={rng.randint(2, 12)} "
            f"rerank_ms={rng.randint(9, 90)} latency_ms={rng.randint(120, 1800)} sample={trace_suffix}"
        ),
        lambda: (
            f"cache: hit_ratio={rng.choice(['0.11', '0.38', '0.52', '0.79'])} "
            f"candidate_count={rng.randint(4, 28)} route={rng.choice(['answer', 'retrieve', 'retry', 'fallback'])} "
            f"shard={request_suffix}"
        ),
    ]
    if profile == "chinese":
        line_builders.append(
            lambda: f"错误：{rng.choice(['上下文过长', '检索超时', '工具返回部分结果'])}，保留最近一次执行输出作为摘要。"
        )
    selected_builders = rng.sample(line_builders, k=min(4, len(line_builders)))
    return "\n".join(build_line() for build_line in selected_builders)


def make_markdown_tail(
    seed: SeedMaterial,
    rng: random.Random,
    profile: str,
    topic: str,
    intent: str,
    app: str,
    category: str,
) -> str:
    bullet_pool = [
        f"- keep the {topic} incident context visible for {app}",
        f"- preserve the latest {intent} failure details in {category}",
        f"- keep the response grounded in recent {topic} tool output for {app}",
        f"- retain the rerank evidence and the final {intent} decision path in {category}",
        f"- annotate whether the retry changed the {topic} outcome for {app}",
        f"- surface the strongest warehouse or metrics signal for {topic} in {category}",
        f"- note the uncertainty instead of padding the {intent} answer for {app}",
        f"- preserve only the highest-signal {topic} artifact excerpts for {category}",
        f"- keep the final summary tied to the active {intent} workflow stage in {app}",
    ]
    if profile == "chinese":
        bullet_pool.extend(
            [
                f"- 保留 {app} 中 {topic} 最近的错误上下文",
                f"- 不要丢失最近一次与 {intent} 相关的执行输出",
                f"- 只引用 {category} 下 {topic} 的最高信号检索证据",
                f"- 说明 retry 是否真的改变了 {topic} 在 {app} 中的结果",
            ]
        )
    return "\n".join(rng.sample(bullet_pool, k=min(rng.randint(2, 4), len(bullet_pool))))


def build_phrase_injection(profile: str, positive_phrase: str | None, negative_phrase: str | None) -> str:
    lines: List[str] = []
    if positive_phrase:
        if profile == "chinese":
            lines.append(f"检索命中信号：{positive_phrase}")
        else:
            lines.append(f"Relevant signal: {positive_phrase}")
    if negative_phrase:
        if profile == "chinese":
            lines.append(f"硬负样本提示：不要把 `{negative_phrase}` 当作真正问题根因。")
        else:
            lines.append(f"Hard negative: do not treat `{negative_phrase}` as the real root cause.")
    return "\n".join(lines)


def build_reasoning_text(
    seed: SeedMaterial,
    rng: random.Random,
    topic: str,
    category: str,
    archetype: str,
    intent: str,
    request_id: str,
    trace_id: str,
    turn_idx: int,
) -> str:
    base = seed_fragment(rng, seed.thinking_snippets)
    request_suffix = request_id[-4:]
    trace_suffix = trace_id[-4:]
    return recursive_sanitize(
        f"{base} I am on turn={turn_idx + 1} for topic={topic}, category={category}, archetype={archetype}. "
        f"Next I should align the answer with intent={intent}, rid={request_suffix}, tid={trace_suffix}."
    )


def build_assistant_text(
    seed: SeedMaterial,
    rng: random.Random,
    topic: str,
    category: str,
    archetype: str,
    intent: str,
    tool_count: int,
    turn_idx: int,
) -> str:
    base = seed_fragment(rng, seed.text_snippets)
    return recursive_sanitize(
        f"{base} Summary focus={topic}; category={category}; archetype={archetype}; intent={intent}. "
        f"This step closes turn={turn_idx + 1} after {tool_count} planned tool call(s)."
    )


def make_context_block_rich(
    seed: SeedMaterial,
    rng: random.Random,
    profile: str,
    topic: str,
    category: str,
    app: str,
    tenant: str,
    archetype: str,
    intent: str,
    request_id: str,
    trace_id: str,
) -> str:
    request_suffix = request_id[-4:]
    trace_suffix = trace_id[-4:]
    if profile == "chinese":
        return (
            f"上下文主题：{topic}；分类：{category}；应用：{app}；租户：{tenant}；"
            f"archetype={archetype}；intent={intent}；"
            f"rid={request_suffix}；tid={trace_suffix}"
        )
    if profile == "mixed":
        return (
            f"Topic={topic}; category={category}; app={app}; tenant={tenant}; "
            f"intent={intent}; archetype={archetype}; "
            f"corr=rid:{request_suffix} tid:{trace_suffix}"
        )
    if profile == "code_log":
        return (
            f"context: topic={topic} category={category} app={app} tenant={tenant} "
            f"intent={intent} archetype={archetype} "
            f"corr=rid:{request_suffix} tid:{trace_suffix}"
        )
    return (
        f"Context for {topic}: app={app}, tenant={tenant}, category={category}.\n"
        f"intent={intent}; archetype={archetype}; corr=rid:{request_suffix}/tid:{trace_suffix}."
    )


def compose_long_text(
    seed: SeedMaterial,
    rng: random.Random,
    topic: str,
    category: str,
    app: str,
    tenant: str,
    archetype: str,
    intent: str,
    profile: str,
    request_id: str,
    trace_id: str,
    target_chars: int,
    positive_phrase: str | None = None,
    negative_phrase: str | None = None,
) -> str:
    parts: List[str] = []
    seen_blocks = set()
    current_length = 0

    def append_block(block: str) -> bool:
        block_key = normalize_text_for_reuse(block[:512])
        if block_key in seen_blocks:
            return False
        nonlocal current_length
        if parts:
            current_length += 2
        current_length += len(block)
        parts.append(block)
        seen_blocks.add(block_key)
        return True

    append_block(
        make_context_block_rich(
            seed, rng, profile, topic, category, app, tenant, archetype, intent, request_id, trace_id
        )
    )
    append_block(make_task_block(topic, category, app, tenant, archetype, intent, profile))
    phrase_block = build_phrase_injection(profile, positive_phrase, negative_phrase)
    if phrase_block:
        append_block(phrase_block)

    seed_blocks: List[Callable[[], str]] = [
        lambda: make_noisy_artifact(seed, rng, request_id, trace_id, profile),
        lambda: make_markdown_tail(seed, rng, profile, topic, intent, app, category),
        lambda: seed_fragment(rng, seed.tool_result_snippets),
        lambda: seed_fragment(rng, seed.thinking_snippets),
        lambda: seed_fragment(rng, seed.text_snippets),
    ]
    rng.shuffle(seed_blocks)
    for build_block in seed_blocks[: rng.randint(2, 4)]:
        append_block(build_block())

    request_suffix = request_id[-4:]
    trace_suffix = trace_id[-4:]
    while current_length < target_chars:
        pad_block = (
            f"{seed_fragment(rng, seed.text_snippets)}\n"
            f"{seed_fragment(rng, seed.tool_result_snippets)}\n"
            f"ctx=rid:{request_suffix} tid:{trace_suffix} topic:{topic} intent:{intent} slot:{len(parts)}"
        )
        if not append_block(pad_block):
            append_block(
                f"{seed_fragment(rng, seed.thinking_snippets)}\n"
                f"ctx=rid:{request_suffix} tid:{trace_suffix} slot:{len(parts)}"
            )
    combined = "\n\n".join(parts)
    return recursive_sanitize(combined[:target_chars])


def is_retrieval_tool(tool_name: str | None) -> bool:
    if not tool_name:
        return False
    lowered = tool_name.lower()
    return any(hint in lowered for hint in RETRIEVAL_TOOL_HINTS)


def generate_request_headers(seed: SeedMaterial, request_id: str, trace_id: str, provider: str) -> Dict[str, str]:
    headers = dict(seed.request_headers)
    if provider != "anthropic":
        headers.pop("anthropic-version", None)
    headers["x-request-id"] = request_id
    headers["x-trace-id"] = trace_id
    headers["authorization"] = "Bearer sk_live_redacted"
    return headers


def sample_tool_defs(
    seed: SeedMaterial,
    rng: random.Random,
    count: int,
    category: str | None = None,
    archetype: str | None = None,
) -> List[Dict[str, Any]]:
    if count <= 0:
        return []

    preferred_tokens = set(TOOL_PREFERENCES_BY_CATEGORY.get(category or "", ())) | set(
        TOOL_PREFERENCES_BY_ARCHETYPE.get(archetype or "", ())
    )
    preferred = [
        tool for tool in seed.tools if any(token in tool.get("name", "").lower() for token in preferred_tokens)
    ]
    remaining = [tool for tool in seed.tools if tool not in preferred]
    rng.shuffle(preferred)
    rng.shuffle(remaining)

    selected: List[Dict[str, Any]] = []
    preferred_budget = min(len(preferred), count, max(1, count - max(1, count // 3)))
    for tool in preferred[:preferred_budget]:
        if tool not in selected:
            selected.append(tool)
    remaining_budget = count - len(selected)
    if remaining_budget > 0:
        for tool in remaining[:remaining_budget]:
            if tool not in selected:
                selected.append(tool)
    if len(selected) < count:
        for pool in (preferred[preferred_budget:], remaining[remaining_budget:]):
            for tool in pool:
                if tool not in selected:
                    selected.append(tool)
                if len(selected) >= count:
                    return copy.deepcopy(selected[:count])
    if preferred and remaining and count >= 3 and rng.random() < 0.35:
        unseen_remaining = [tool for tool in remaining if tool not in selected]
        if unseen_remaining:
            swap_out = rng.randrange(len(selected))
            selected[swap_out] = rng.choice(unseen_remaining)
    return copy.deepcopy(selected[:count])


def request_profile(archetype: str, request_kind: str) -> Dict[str, Tuple[int, int]]:
    tool_ranges = {
        "simple_chat": (0, 0),
        "tool_lookup": (1, 3),
        "research_agent": (3, 8),
        "retry_after_429": (1, 4),
        "timeout_then_fallback": (1, 5),
        "guardrail_block": (0, 2),
        "large_context_replay": (1, 6),
    }
    generation_ranges = {
        "simple_chat": (1, 2),
        "tool_lookup": (1, 3),
        "research_agent": (2, 6),
        "retry_after_429": (2, 4),
        "timeout_then_fallback": (2, 4),
        "guardrail_block": (1, 2),
        "large_context_replay": (1, 3),
    }
    if request_kind == "tool_heavy_generation":
        tool_ranges = dict(tool_ranges)
        tool_ranges[archetype] = (max(2, tool_ranges[archetype][0]), max(4, tool_ranges[archetype][1]))
    if request_kind == "long_context_generation":
        generation_ranges = dict(generation_ranges)
        generation_ranges[archetype] = (max(2, generation_ranges[archetype][0]), max(4, generation_ranges[archetype][1] + 2))
    return {
        "tool_range": tool_ranges[archetype],
        "generation_range": generation_ranges[archetype],
    }


def choose_intent_and_display(rng: random.Random, archetype: str) -> Tuple[str, str]:
    if archetype in {"tool_lookup", "simple_chat"} and rng.random() < 0.5:
        return rng.choice(["reply", "engage"]), rng.choice(["reply", "comment", "post", "回复", "帖子"])
    if archetype in {"research_agent", "large_context_replay"}:
        return rng.choice(["explore", "research", "investigate"]), rng.choice(["research", "explore", "discover", "community", "调研", "检索"])
    return rng.choice(["reply", "engage", "explore", "research", "investigate"]), rng.choice(["reply", "comment", "research", "discover"])


def inject_text_profile_values(rng: random.Random, body: Dict[str, Any], profile: str) -> None:
    if rng.random() < 0.70:
        body["temperature"] = round(rng.uniform(0.1, 0.95), 2)
    if rng.random() < 0.55:
        body["top_p"] = round(rng.uniform(0.7, 0.99), 2)


def build_messages_call(
    seed: SeedMaterial,
    rng: random.Random,
    call_idx: int,
    trace_id: str,
    session_id: str,
    timestamp: datetime,
    tenant: str,
    app: str,
    model: str,
    archetype: str,
    request_kind: str,
    category: str,
    text_profile: str,
    positive_phrase: str | None,
    negative_phrase: str | None,
    huge_remaining: List[int],
) -> Dict[str, Any]:
    request_id = deterministic_uuid("req", call_idx)
    provider = choose_provider_for_call(rng, "/v1/messages", model)
    profile = request_profile(archetype, request_kind)
    tool_count = rng.randint(*profile["tool_range"])
    turn_count = rng.randint(*profile["generation_range"])
    tool_defs = sample_tool_defs(
        seed,
        rng,
        max(1, tool_count if tool_count > 0 else rng.randint(1, 3)),
        category=category,
        archetype=archetype,
    )
    topic = rng.choice(TOPIC_POOLS.get(category, ["incident review", "workflow replay", "customer answer"]))
    intent, display_text = choose_intent_and_display(rng, archetype)

    template = copy.deepcopy(seed.messages_template)
    body = template["request"]["body"]
    body["model"] = model
    body["messages"] = []
    body["system"] = seed.system_prompt
    body["tools"] = tool_defs
    body["metadata"] = {
        "trace_id": trace_id,
        "tenant": tenant,
        "app": app,
        "task_category": category,
        "trace_archetype": archetype,
        "language_profile": text_profile,
        "request_kind": request_kind,
        "workflow_variant": workflow_variant_for(archetype, request_kind),
        "provider": provider,
    }
    body["max_tokens"] = 4096 if archetype != "guardrail_block" else 1024
    body["thinking"] = {"type": "enabled", "budget_tokens": 2048}
    body["stream"] = rng.random() < 0.70
    inject_text_profile_values(rng, body, text_profile)
    current_body_size = body_size_bytes(body)
    message_sizes: List[int] = []

    response_content: List[Dict[str, Any]] = [
        {
            "type": "thinking",
            "thinking": build_reasoning_text(
                seed, rng, topic, category, archetype, intent, request_id, trace_id, turn_idx=0
            )[:3000],
        }
    ]
    tool_use_count = 0
    request_messages = body["messages"]
    for turn_idx in range(turn_count):
        user_text = compose_long_text(
            seed=seed,
            rng=rng,
            topic=topic,
            category=category,
            app=app,
            tenant=tenant,
            archetype=archetype,
            intent=intent,
            profile=text_profile,
            request_id=request_id,
            trace_id=trace_id,
            target_chars=rng.randint(2000, 9000 if request_kind != "long_context_generation" else 24000),
            positive_phrase=positive_phrase if turn_idx == 0 else None,
            negative_phrase=negative_phrase if turn_idx == 1 else None,
        )
        current_body_size += append_message_with_size(
            request_messages,
            message_sizes,
            {"role": "user", "content": [{"type": "text", "text": user_text}]},
        )

        assistant_content: List[Dict[str, Any]] = [
            {
                "type": "thinking",
                "thinking": build_reasoning_text(
                    seed, rng, topic, category, archetype, intent, request_id, trace_id, turn_idx
                )[:2500],
            }
        ]
        if tool_use_count < tool_count:
            tool_def = tool_defs[tool_use_count % len(tool_defs)]
            tool_use = {
                "type": "tool_use",
                "id": f"toolu_{call_idx:06d}_{tool_use_count:02d}",
                "name": tool_def["name"],
                "input": {
                    "user_intent": intent,
                    "display_text": display_text,
                    "target": f"/workspace/demo/{app}/{trace_id}/{request_id}/{tool_def['name'].lower()}_{tool_use_count}.md",
                    "cwd": f"/workspace/{tenant}/{app}",
                    "env": {"APP_NAME": app} if rng.random() < 0.25 else {},
                },
            }
            assistant_content.append(tool_use)
            current_body_size += append_message_with_size(
                request_messages,
                message_sizes,
                {"role": "assistant", "content": assistant_content},
            )
            result_text = compose_long_text(
                seed=seed,
                rng=rng,
                topic=topic,
                category=category,
                app=app,
                tenant=tenant,
                archetype=archetype,
                intent=intent,
                profile="code_log" if text_profile != "chinese" else text_profile,
                request_id=request_id,
                trace_id=trace_id,
                target_chars=rng.randint(1800, 10000),
                positive_phrase=positive_phrase if tool_use_count == 0 else None,
                negative_phrase=negative_phrase if tool_use_count == 1 else None,
            )
            is_error = (
                archetype in {"retry_after_429", "timeout_then_fallback", "guardrail_block"}
                and tool_use_count == 0
            )
            current_body_size += append_message_with_size(
                request_messages,
                message_sizes,
                {
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_use["id"],
                        "content": result_text,
                        "is_error": is_error,
                    }],
                },
            )
            response_content.append({
                "type": "tool_use",
                "id": tool_use["id"],
                "name": tool_use["name"],
                "input": tool_use["input"],
            })
            tool_use_count += 1
        else:
            assistant_content.append({
                "type": "text",
                "text": build_assistant_text(
                    seed, rng, topic, category, archetype, intent, tool_count, turn_idx
                )[:1600],
            })
            current_body_size += append_message_with_size(
                request_messages,
                message_sizes,
                {"role": "assistant", "content": assistant_content},
            )

    response_content.append({
        "type": "text",
        "text": build_assistant_text(seed, rng, topic, category, archetype, intent, tool_count, turn_count)[:1600],
    })

    target_min, target_max, bucket_label = pick_body_bucket(rng, "/v1/messages", huge_remaining)
    while current_body_size < target_min:
        remaining_bytes = target_min - current_body_size
        filler = compose_long_text(
            seed,
            rng,
            topic,
            category,
            app,
            tenant,
            archetype,
            intent,
            text_profile,
            request_id,
            trace_id,
            target_chars=min(20000, max(2500, remaining_bytes // 2)),
        )
        current_body_size += append_message_with_size(
            request_messages,
            message_sizes,
            {"role": "user", "content": [{"type": "text", "text": filler}]},
        )
        current_body_size += append_message_with_size(
            request_messages,
            message_sizes,
            {
                "role": "assistant",
                "content": [{
                    "type": "thinking",
                    "thinking": build_reasoning_text(
                        seed, rng, topic, category, archetype, intent, request_id, trace_id, len(request_messages)
                    )[:2500],
                }],
            },
        )
        if len(request_messages) > 120:
            break
    while current_body_size > target_max and len(request_messages) > 6:
        current_body_size -= pop_message_with_size(request_messages, message_sizes)

    stop_reason = "tool_use" if tool_count > 0 else rng.choice(["stop", "end_turn", "max_tokens"])
    http_status = 200
    if archetype == "retry_after_429" and rng.random() < 0.65:
        http_status = 429
        stop_reason = "error"
    elif archetype == "guardrail_block":
        http_status = 400
        stop_reason = "error"

    usage = {
        "input_tokens": max(100, current_body_size // 4),
        "output_tokens": 0 if http_status >= 400 else max(50, current_body_size // 10),
        "cache_read_input_tokens": 0 if http_status >= 400 else rng.randint(0, 800),
    }
    envelope = template
    envelope["request_id"] = request_id
    envelope["timestamp"] = timestamp.isoformat().replace("+00:00", "Z")
    envelope["agent_name"] = "matrix_agent_bench"
    envelope["request"]["method"] = "POST"
    envelope["request"]["url"] = f"{PROVIDER_BASE_URLS[provider]}/v1/messages"
    envelope["request"]["path"] = "/v1/messages"
    envelope["request"]["headers"] = generate_request_headers(seed, request_id, trace_id, provider)
    envelope["request"]["body"] = body
    envelope["filtered_request"] = {"path": "/v1/messages", "model": model}
    envelope["response"]["status"] = http_status
    envelope["response"]["headers"] = {**seed.response_headers, "x-response-id": deterministic_uuid("resp", call_idx)}
    if http_status >= 400:
        error_type = "rate_limit_error" if http_status == 429 else "guardrail_error"
        envelope["response"]["body"] = {
            "type": "error",
            "error": {
                "type": error_type,
                "code": "rate_limited" if http_status == 429 else "policy_blocked",
                "message": (
                    "Rate limit exceeded; retry with backoff."
                    if http_status == 429
                    else "Request blocked by policy guardrail."
                ),
                "retryable": http_status == 429,
                "rule_id": (
                    f"rl_{request_id[-6:]}"
                    if http_status == 429
                    else f"guardrail_{workflow_variant_for(archetype, request_kind)}_{request_id[-4:]}"
                ),
                "retry_after_ms": rng.choice([800, 1200, 1800, 2400]) if http_status == 429 else None,
            },
            "usage": usage,
        }
    else:
        envelope["response"]["body"] = {
            "id": deterministic_uuid("msg", call_idx),
            "content": response_content,
            "model": model,
            "role": "assistant",
            "stop_reason": stop_reason,
            "type": "message",
            "usage": usage,
        }
    envelope["duration_ms"] = rng.randint(400, 12000 if archetype in {"research_agent", "large_context_replay"} else 5000)
    envelope["is_streaming"] = bool(body["stream"])
    envelope["trace_id"] = trace_id
    envelope["session_id"] = session_id
    envelope["tenant"] = tenant
    envelope["app"] = app
    envelope["environment"] = weighted_choice(rng, ENVIRONMENT_WEIGHTS)
    envelope["task_category"] = category
    envelope["trace_archetype"] = archetype
    envelope["request_kind"] = request_kind
    envelope["language_profile"] = text_profile
    envelope["provider"] = provider
    envelope["size_bucket"] = bucket_label
    return {
        "event_time": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "biz_date": timestamp.strftime("%Y-%m-%d"),
        "request_id": request_id,
        "session_id": session_id,
        "request_path": "/v1/messages",
        "model": model,
        "http_status": http_status,
        "stop_reason": stop_reason,
        "source": provider,
        "tenant": tenant,
        "v": envelope,
    }


def build_count_tokens_call(
    seed: SeedMaterial,
    rng: random.Random,
    call_idx: int,
    trace_id: str,
    session_id: str,
    timestamp: datetime,
    tenant: str,
    app: str,
    model: str,
    archetype: str,
    category: str,
    text_profile: str,
    positive_phrase: str | None,
    negative_phrase: str | None,
    huge_remaining: List[int],
) -> Dict[str, Any]:
    request_id = deterministic_uuid("req", call_idx)
    provider = choose_provider_for_call(rng, "/v1/messages/count_tokens", model)
    if rng.random() < 0.95:
        content: Any = compose_long_text(
            seed,
            rng,
            topic="token estimate",
            category=category,
            app=app,
            tenant=tenant,
            archetype=archetype,
            intent="estimate_tokens",
            profile=text_profile,
            request_id=request_id,
            trace_id=trace_id,
            target_chars=2500,
            positive_phrase=positive_phrase,
            negative_phrase=negative_phrase,
        )
    else:
        content = [{"type": "text", "text": seed_fragment(rng, seed.count_token_snippets)[:400]}]

    template = copy.deepcopy(seed.count_tokens_template)
    body = template["request"]["body"]
    body["model"] = model
    body["messages"] = [{"role": "user", "content": content}]
    body["tools"] = []
    body["metadata"] = {
        "trace_id": trace_id,
        "tenant": tenant,
        "app": app,
        "task_category": category,
        "trace_archetype": archetype,
        "language_profile": text_profile,
        "request_kind": "count_tokens",
        "workflow_variant": workflow_variant_for(archetype, "count_tokens"),
        "provider": provider,
    }
    inject_text_profile_values(rng, body, text_profile)
    target_min, target_max, bucket_label = pick_body_bucket(rng, "/v1/messages/count_tokens", huge_remaining)
    while body_size_bytes(body) < target_min:
        current = body["messages"][0]
        if isinstance(current["content"], str):
            current["content"] += "\n" + seed_fragment(rng, seed.count_token_snippets)
            current["content"] += "\n" + compose_long_text(
                seed,
                rng,
                topic="count tokens",
                category=category,
                app=app,
                tenant=tenant,
                archetype=archetype,
                intent="estimate_tokens",
                profile=text_profile,
                request_id=request_id,
                trace_id=trace_id,
                target_chars=min(8000, target_min - body_size_bytes(body) + 2000),
            )
        else:
            current["content"].append({"type": "text", "text": seed_fragment(rng, seed.count_token_snippets)})
        if body_size_bytes(body) > target_max:
            break
    while body_size_bytes(body) > target_max:
        current = body["messages"][0]
        if isinstance(current["content"], str):
            current["content"] = current["content"][:target_max]
            break
        if len(current["content"]) > 1:
            current["content"].pop()
        else:
            break

    input_tokens = max(50, body_size_bytes(body) // 5)
    envelope = template
    envelope["request_id"] = request_id
    envelope["timestamp"] = timestamp.isoformat().replace("+00:00", "Z")
    envelope["agent_name"] = "matrix_agent_bench"
    envelope["request"]["method"] = "POST"
    envelope["request"]["url"] = f"{PROVIDER_BASE_URLS[provider]}/v1/messages/count_tokens"
    envelope["request"]["path"] = "/v1/messages/count_tokens"
    envelope["request"]["headers"] = generate_request_headers(seed, request_id, trace_id, provider)
    envelope["request"]["body"] = body
    envelope["filtered_request"] = {"path": "/v1/messages/count_tokens", "model": model}
    envelope["response"]["status"] = 200
    envelope["response"]["headers"] = {**seed.response_headers, "x-response-id": deterministic_uuid("resp", call_idx)}
    envelope["response"]["body"] = {"input_tokens": input_tokens, "model": model}
    envelope["duration_ms"] = rng.randint(80, 900)
    envelope["is_streaming"] = False
    envelope["trace_id"] = trace_id
    envelope["session_id"] = session_id
    envelope["tenant"] = tenant
    envelope["app"] = app
    envelope["environment"] = weighted_choice(rng, ENVIRONMENT_WEIGHTS)
    envelope["task_category"] = category
    envelope["trace_archetype"] = archetype
    envelope["request_kind"] = "count_tokens"
    envelope["language_profile"] = text_profile
    envelope["provider"] = provider
    envelope["size_bucket"] = bucket_label
    return {
        "event_time": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "biz_date": timestamp.strftime("%Y-%m-%d"),
        "request_id": request_id,
        "session_id": session_id,
        "request_path": "/v1/messages/count_tokens",
        "model": model,
        "http_status": 200,
        "stop_reason": "stop",
        "source": provider,
        "tenant": tenant,
        "v": envelope,
    }


def build_tool_observations(raw: Dict[str, Any], generation_id: str, seq_counter: Dict[str, int]) -> Tuple[List[Dict[str, Any]], Counter]:
    trace_id = raw["v"]["trace_id"]
    session_id = raw["session_id"]
    v = raw["v"]
    messages = raw["v"]["request"]["body"].get("messages", [])
    tool_uses: Dict[str, Dict[str, Any]] = {}
    tool_results: Dict[str, Dict[str, Any]] = {}
    tool_names = Counter()
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "tool_use":
                tool_uses[item["id"]] = item
                tool_names[item["name"]] += 1
            elif item_type == "tool_result":
                tool_results[item["tool_use_id"]] = item

    observations = []
    child_offset_seconds = 2
    for tool_id, tool_use in tool_uses.items():
        seq_counter[trace_id] += 1
        result = tool_results.get(tool_id, {})
        input_payload = tool_use.get("input", {})
        output_text = recursive_sanitize(str(result.get("content", "")))
        tool_observation_id = observation_uuid(trace_id, seq_counter[trace_id])
        tool_status = "error" if result.get("is_error") else "ok"
        tool_latency = max(40, raw["v"]["duration_ms"] // max(1, len(tool_uses)) + (len(output_text) % 180))
        attr = build_attr(raw, "TOOL", tool_observation_id)
        observations.append({
            "event_time": shift_event_time(raw["event_time"], child_offset_seconds),
            "biz_date": raw["biz_date"],
            "trace_id": trace_id,
            "session_id": session_id,
            "observation_id": tool_observation_id,
            "parent_observation_id": generation_id,
            "seq_no": seq_counter[trace_id],
            "type": "TOOL",
            "status": tool_status,
            "tenant": v["tenant"],
            "app": v["app"],
            "environment": v["environment"],
            "task_category": v["task_category"],
            "trace_archetype": v["trace_archetype"],
            "model": raw["model"],
            "tool_name": tool_use.get("name"),
            "input": json.dumps(input_payload, ensure_ascii=False)[:800],
            "output": str(output_text)[:1200],
            "latency_ms": tool_latency,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_cost": 0.0,
            "payload": {
                "context": {
                    "tenant": v["tenant"],
                    "app": v["app"],
                    "environment": v["environment"],
                    "task_category": v["task_category"],
                    "trace_archetype": v["trace_archetype"],
                },
                "attr": attr,
                "links": {
                    "request_id": raw["request_id"],
                    "generation_observation_id": generation_id,
                    "tool_use_id": tool_id,
                },
                "tool_args": input_payload,
                "tool_result": {
                    "stderr": output_text[:600]
                    if result.get("is_error") or ("stderr:" in output_text and stable_seed_int(tool_id) % 4 == 0)
                    else "",
                    "exit_code": 1 if result.get("is_error") else 0,
                    "display_text": input_payload.get("display_text"),
                    "user_intent": input_payload.get("user_intent"),
                },
                **build_telemetry_content(
                    raw,
                    "TOOL",
                    tool_observation_id,
                    attr,
                    tool_status,
                    tool_name=tool_use.get("name"),
                    tool_call_id=tool_id,
                ),
            },
        })
        child_offset_seconds += 1
        if is_retrieval_tool(tool_use.get("name")):
            seq_counter[trace_id] += 1
            retrieval_observation_id = observation_uuid(trace_id, seq_counter[trace_id])
            retrieval_attr = build_attr(raw, "RETRIEVAL", retrieval_observation_id)
            retrieval_status = "error" if result.get("is_error") else "ok"
            observations.append({
                "event_time": shift_event_time(raw["event_time"], child_offset_seconds),
                "biz_date": raw["biz_date"],
                "trace_id": trace_id,
                "session_id": session_id,
                "observation_id": retrieval_observation_id,
                "parent_observation_id": tool_observation_id,
                "seq_no": seq_counter[trace_id],
                "type": "RETRIEVAL",
                "status": retrieval_status,
                "tenant": v["tenant"],
                "app": v["app"],
                "environment": v["environment"],
                "task_category": v["task_category"],
                "trace_archetype": v["trace_archetype"],
                "model": raw["model"],
                "tool_name": tool_use.get("name"),
                "input": str(input_payload.get("target") or input_payload.get("display_text") or "")[:800],
                "output": str(output_text)[:1200],
                "latency_ms": max(12, min(450, tool_latency // 3)),
                "input_tokens": max(4, len(str(input_payload.get("target") or input_payload.get("display_text") or "")) // 12),
                "output_tokens": max(24, len(output_text) // 18),
                "total_cost": 0.0,
                "payload": {
                    "context": {
                        "tenant": v["tenant"],
                        "app": v["app"],
                        "environment": v["environment"],
                        "task_category": v["task_category"],
                        "trace_archetype": v["trace_archetype"],
                    },
                    "attr": retrieval_attr,
                    "links": {
                        "request_id": raw["request_id"],
                        "generation_observation_id": generation_id,
                        "tool_observation_id": tool_observation_id,
                        "tool_use_id": tool_id,
                    },
                    "retrieval": {
                        "target": input_payload.get("target"),
                        "display_text": input_payload.get("display_text"),
                        "user_intent": input_payload.get("user_intent"),
                        "result_preview": output_text[:600],
                    },
                    **build_telemetry_content(
                        raw,
                        "RETRIEVAL",
                        retrieval_observation_id,
                        retrieval_attr,
                        retrieval_status,
                        tool_name=tool_use.get("name"),
                        tool_call_id=tool_id,
                    ),
                },
            })
            child_offset_seconds += 1
    return observations, tool_names


def build_reasoning_observations(raw: Dict[str, Any], generation_id: str, seq_counter: Dict[str, int]) -> List[Dict[str, Any]]:
    content = raw["v"]["response"]["body"].get("content", [])
    if not isinstance(content, list):
        return []

    observations = []
    child_offset_seconds = 1
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "thinking":
            continue
        thinking_text = str(item.get("thinking", "")).strip()
        if not thinking_text:
            continue
        trace_id = raw["v"]["trace_id"]
        v = raw["v"]
        seq_counter[trace_id] += 1
        reasoning_observation_id = observation_uuid(trace_id, seq_counter[trace_id])
        attr = build_attr(raw, "REASONING", reasoning_observation_id)
        output_tokens = max(12, len(thinking_text) // 6)
        latency_ms = max(12, min(350, len(thinking_text) // 8))
        observations.append({
            "event_time": shift_event_time(raw["event_time"], child_offset_seconds),
            "biz_date": raw["biz_date"],
            "trace_id": trace_id,
            "session_id": raw["session_id"],
            "observation_id": reasoning_observation_id,
            "parent_observation_id": generation_id,
            "seq_no": seq_counter[trace_id],
            "type": "REASONING",
            "status": "ok",
            "tenant": v["tenant"],
            "app": v["app"],
            "environment": v["environment"],
            "task_category": v["task_category"],
            "trace_archetype": v["trace_archetype"],
            "model": raw["model"],
            "tool_name": None,
            "input": None,
            "output": thinking_text[:1600],
            "latency_ms": latency_ms,
            "input_tokens": 0,
            "output_tokens": output_tokens,
            "total_cost": round(output_tokens / 500000.0, 6),
            "payload": {
                "context": {
                    "tenant": v["tenant"],
                    "app": v["app"],
                    "environment": v["environment"],
                    "task_category": v["task_category"],
                    "trace_archetype": v["trace_archetype"],
                },
                "attr": attr,
                "links": {
                    "request_id": raw["request_id"],
                    "generation_observation_id": generation_id,
                },
                "reasoning": {
                    "summary": thinking_text[:600],
                },
                **build_telemetry_content(raw, "REASONING", reasoning_observation_id, attr, "ok"),
            },
        })
        child_offset_seconds += 1
    return observations


def build_observations_for_raw(
    raw: Dict[str, Any],
    seq_counter: Dict[str, int],
) -> Tuple[List[Dict[str, Any]], Counter, str, bool]:
    observations: List[Dict[str, Any]] = []
    tool_name_counter = Counter()
    v = raw["v"]
    trace_id = v["trace_id"]
    seq_counter[trace_id] += 1
    generation_id = observation_uuid(trace_id, seq_counter[trace_id])
    response_body = v["response"]["body"]
    usage = response_body.get("usage", {})
    request_body = v["request"]["body"]
    if raw["request_path"] == "/v1/messages":
        first_input = request_body["messages"][0]["content"][0]["text"]
        if "content" in response_body:
            output_text = json.dumps(response_body.get("content", []), ensure_ascii=False)
        elif "error" in response_body:
            output_text = json.dumps(response_body["error"], ensure_ascii=False)
        else:
            output_text = json.dumps(response_body, ensure_ascii=False)
    else:
        first_input = str(request_body["messages"][0]["content"])
        output_text = str(response_body)
    top_level_type = "GENERATION" if raw["request_path"] == "/v1/messages" else "TOKEN_ESTIMATE"
    top_level_status = "error" if raw["http_status"] >= 400 else "ok"
    attr = build_attr(raw, top_level_type, generation_id)
    observations.append({
        "event_time": raw["event_time"],
        "biz_date": raw["biz_date"],
        "trace_id": trace_id,
        "session_id": raw["session_id"],
        "observation_id": generation_id,
        "parent_observation_id": None,
        "seq_no": seq_counter[trace_id],
        "type": top_level_type,
        "status": top_level_status,
        "tenant": v["tenant"],
        "app": v["app"],
        "environment": v["environment"],
        "task_category": v["task_category"],
        "trace_archetype": v["trace_archetype"],
        "model": raw["model"],
        "tool_name": None,
        "input": first_input[:1200],
        "output": output_text[:1600],
        "latency_ms": v["duration_ms"],
        "input_tokens": usage.get("input_tokens", response_body.get("input_tokens", 0)),
        "output_tokens": usage.get("output_tokens", 0),
        "total_cost": round((usage.get("input_tokens", 0) + usage.get("output_tokens", 0)) / 100000.0, 6),
        "payload": {
            "provider": {
                "stop_reason": raw["stop_reason"],
                "response_id": v["response"]["headers"]["x-response-id"],
                "cache_hit": usage.get("cache_read_input_tokens", 0) > 0,
            },
            "generation_config": {
                "temperature": request_body.get("temperature"),
                "top_p": request_body.get("top_p"),
                "max_tokens": request_body.get("max_tokens"),
                "stream": request_body.get("stream"),
            },
            "attr": attr,
            "links": {
                "request_id": raw["request_id"],
                "request_path": raw["request_path"],
            },
            "context": {
                "tenant": v["tenant"],
                "app": v["app"],
                "task_category": v["task_category"],
                "trace_archetype": v["trace_archetype"],
                "language_profile": v["language_profile"],
                "environment": v["environment"],
            },
            **build_telemetry_content(raw, top_level_type, generation_id, attr, top_level_status),
        },
    })
    observations.extend(build_reasoning_observations(raw, generation_id, seq_counter))
    has_tool_error = False
    if raw["request_path"] == "/v1/messages":
        tool_obs, tool_names = build_tool_observations(raw, generation_id, seq_counter)
        observations.extend(tool_obs)
        tool_name_counter.update(tool_names)
        has_tool_error = any(obs["status"] == "error" for obs in tool_obs if obs["type"] == "TOOL")
    if raw["http_status"] >= 400 or raw["stop_reason"] in {"max_tokens", "error"}:
        seq_counter[trace_id] += 1
        event_type = "GUARDRAIL" if v["trace_archetype"] == "guardrail_block" else "EVENT"
        event_observation_id = observation_uuid(trace_id, seq_counter[trace_id])
        event_attr = build_attr(raw, event_type, event_observation_id)
        observations.append({
            "event_time": shift_event_time(raw["event_time"], 90),
            "biz_date": raw["biz_date"],
            "trace_id": trace_id,
            "session_id": raw["session_id"],
            "observation_id": event_observation_id,
            "parent_observation_id": generation_id,
            "seq_no": seq_counter[trace_id],
            "type": event_type,
            "status": "warn",
            "tenant": v["tenant"],
            "app": v["app"],
            "environment": v["environment"],
            "task_category": v["task_category"],
            "trace_archetype": v["trace_archetype"],
            "model": raw["model"],
            "tool_name": None,
            "input": None,
            "output": raw["stop_reason"],
            "latency_ms": max(6, min(180, raw["v"]["duration_ms"] // 12)),
            "input_tokens": 0,
            "output_tokens": 0,
            "total_cost": 0.0,
            "payload": {
                "context": {
                    "tenant": v["tenant"],
                    "app": v["app"],
                    "environment": v["environment"],
                    "task_category": v["task_category"],
                    "trace_archetype": v["trace_archetype"],
                },
                "attr": event_attr,
                "links": {
                    "request_id": raw["request_id"],
                    "generation_observation_id": generation_id,
                },
                "event": {
                    "http_status": raw["http_status"],
                    "stop_reason": raw["stop_reason"],
                    "trace_archetype": v["trace_archetype"],
                    "error_kind": "http_error" if raw["http_status"] >= 400 else "generation_stop",
                },
                **build_telemetry_content(raw, event_type, event_observation_id, event_attr, "warn"),
            },
        })
    return observations, tool_name_counter, generation_id, has_tool_error


def compile_observations(raw_calls: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Counter]:
    observations: List[Dict[str, Any]] = []
    seq_counter: Dict[str, int] = defaultdict(int)
    tool_name_counter = Counter()
    for raw in raw_calls:
        row_observations, row_tool_names, _, _ = build_observations_for_raw(raw, seq_counter)
        observations.extend(row_observations)
        tool_name_counter.update(row_tool_names)
    return observations, tool_name_counter


def quantiles(values: List[int]) -> Dict[str, float]:
    if not values:
        return {"min": 0, "p50": 0, "p95": 0, "max": 0}
    ordered = sorted(values)
    return {
        "min": ordered[0],
        "p50": ordered[len(ordered) // 2],
        "p95": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
        "max": ordered[-1],
    }


def count_bucket(label: str, counter: Counter) -> None:
    counter[label] += 1


@lru_cache(maxsize=32768)
def normalize_text_for_reuse(value: str) -> str:
    return " ".join(value.split())


def build_text_reuse_summary(observations: List[Dict[str, Any]]) -> Dict[str, Any]:
    reusable_texts: List[str] = []
    reusable_lines: List[str] = []
    for observation in observations:
        if observation["type"] in {"EVENT", "GUARDRAIL"}:
            continue
        for field in ("input", "output"):
            value = observation.get(field)
            if isinstance(value, str) and len(value.strip()) >= 40:
                normalized = normalize_text_for_reuse(value)
                reusable_texts.append(normalized)
                for line in value.splitlines():
                    normalized_line = normalize_text_for_reuse(line)
                    if (
                        len(normalized_line) >= 24
                        and not normalized_line.startswith("`request_id=")
                        and not normalized_line.startswith("`trace_id=")
                    ):
                        reusable_lines.append(normalized_line)
    counter = Counter(reusable_texts)
    line_counter = Counter(reusable_lines)
    duplicate_groups = [count for count in counter.values() if count > 1]
    duplicate_rows = sum(count - 1 for count in duplicate_groups)
    total_texts = len(reusable_texts)
    return {
        "meaningful_text_count": total_texts,
        "duplicate_group_count": len(duplicate_groups),
        "duplicate_row_count": duplicate_rows,
        "duplicate_ratio": round(duplicate_rows / max(1, total_texts), 3),
        "max_reuse_count": max(counter.values(), default=1),
        "max_line_reuse_count": max(line_counter.values(), default=1),
        "reused_line_count": sum(1 for count in line_counter.values() if count > 8),
    }


def build_summary(
    raw_calls: List[Dict[str, Any]],
    observations: List[Dict[str, Any]],
    tool_name_counter: Counter,
    strong_labels: Counter,
    negative_labels: Counter,
) -> Dict[str, Any]:
    request_path_counter = Counter()
    tenant_counter = Counter()
    app_counter = Counter()
    model_counter = Counter()
    source_counter = Counter()
    archetype_counter = Counter()
    request_kind_counter = Counter()
    language_counter = Counter()
    message_bucket_counter = Counter()
    count_bucket_counter = Counter()
    message_lengths = []
    tool_lengths = []
    trace_tool_counts = Counter()
    trace_generation_counts = Counter()
    trace_archetype_trace_counts = Counter()
    error_text_distribution = Counter()
    strong_injected_rows = 0
    negative_injected_rows = 0
    trace_status = {}
    planned_positive_phrase_by_request: Dict[str, str] = {}
    planned_negative_phrase_by_request: Dict[str, str] = {}
    planned_positive_family_by_request: Dict[str, str] = {}
    planned_negative_family_by_request: Dict[str, str] = {}

    for raw in raw_calls:
        v = raw["v"]
        request_path_counter[raw["request_path"]] += 1
        tenant_counter[v["tenant"]] += 1
        app_counter[v["app"]] += 1
        model_counter[raw["model"]] += 1
        source_counter[raw["source"]] += 1
        archetype_counter[v["trace_archetype"]] += 1
        trace_archetype_trace_counts[v["trace_archetype"]] += 0
        request_kind_counter[v["request_kind"]] += 1
        language_counter[v["language_profile"]] += 1
        body = v["request"]["body"]
        message_lengths.append(len(body.get("messages", [])))
        tool_lengths.append(len(body.get("tools", [])))
        trace_generation_counts[v["trace_id"]] = trace_generation_counts.get(v["trace_id"], 0) + 1
        if trace_generation_counts[v["trace_id"]] == 1:
            trace_archetype_trace_counts[v["trace_archetype"]] += 1
        if raw["request_path"] == "/v1/messages":
            count_bucket(v["size_bucket"], message_bucket_counter)
        else:
            count_bucket(v["size_bucket"], count_bucket_counter)
        if raw["http_status"] >= 400:
            trace_status[v["trace_id"]] = "failed"
        labels = v.get("benchmark_labels", {})
        if labels.get("positive_phrase"):
            strong_injected_rows += 1
            error_text_distribution[labels["positive_phrase"]] += 1
            planned_positive_phrase_by_request[raw["request_id"]] = labels["positive_phrase"]
            planned_positive_family_by_request[raw["request_id"]] = labels.get("positive_family", "unknown")
        if labels.get("negative_phrase"):
            negative_injected_rows += 1
            planned_negative_phrase_by_request[raw["request_id"]] = labels["negative_phrase"]
            planned_negative_family_by_request[raw["request_id"]] = labels.get("negative_family", "unknown")

    obs_type_counter = Counter(obs["type"] for obs in observations)
    obs_status_counter = Counter(obs["status"] for obs in observations)
    generation_rows = [obs for obs in observations if obs["type"] == "GENERATION"]
    top_level_rows = [obs for obs in observations if obs["parent_observation_id"] is None]
    tool_rows = [obs for obs in observations if obs["type"] == "TOOL"]
    event_rows = [obs for obs in observations if obs["type"] == "EVENT"]

    generation_attr_cov = {
        "temperature_ratio": round(sum(1 for obs in generation_rows if obs["payload"]["generation_config"].get("temperature") is not None) / max(1, len(generation_rows)), 3),
        "top_p_ratio": round(sum(1 for obs in generation_rows if obs["payload"]["generation_config"].get("top_p") is not None) / max(1, len(generation_rows)), 3),
        "provider_stop_reason_ratio": round(sum(1 for obs in generation_rows if obs["payload"]["provider"].get("stop_reason")) / max(1, len(generation_rows)), 3),
        "cache_hit_ratio": round(sum(1 for obs in generation_rows if obs["payload"]["provider"].get("cache_hit")) / max(1, len(generation_rows)), 3),
        "provider_response_id_ratio": round(sum(1 for obs in generation_rows if obs["payload"]["provider"].get("response_id")) / max(1, len(generation_rows)), 3),
    }
    tool_attr_cov = {
        "cwd_ratio": round(sum(1 for obs in tool_rows if obs["payload"]["tool_args"].get("cwd")) / max(1, len(tool_rows)), 3),
        "env_ratio": round(sum(1 for obs in tool_rows if obs["payload"]["tool_args"].get("env")) / max(1, len(tool_rows)), 3),
        "stderr_ratio": round(sum(1 for obs in tool_rows if obs["payload"]["tool_result"].get("stderr")) / max(1, len(tool_rows)), 3),
    }
    attr_key_counter = Counter()
    attr_presence_counter = Counter()
    attr_count_per_observation: List[int] = []
    actual_positive_requests = set()
    actual_negative_requests = set()
    actual_positive_observation_ids: List[str] = []
    actual_negative_observation_ids: List[str] = []
    actual_positive_family_counter = Counter()
    actual_negative_family_counter = Counter()
    telemetry_counter = Counter()
    for obs in observations:
        attr = obs["payload"].get("attr", {})
        attr_count_per_observation.append(len(attr))
        for key in attr:
            attr_key_counter[key] += 1
        for key in DYNAMIC_CORE_FIELD_POOLS:
            if key in attr:
                attr_presence_counter[key] += 1
        for key in ("resource", "scope", "otel", "langfuse", "mlflow"):
            if key in obs["payload"]:
                telemetry_counter[key] += 1
        serialized = json.dumps(
            {"input": obs.get("input"), "output": obs.get("output"), "payload": obs.get("payload", {})},
            ensure_ascii=False,
        )
        request_id = obs["payload"]["links"]["request_id"]
        planned_positive_phrase = planned_positive_phrase_by_request.get(request_id)
        planned_negative_phrase = planned_negative_phrase_by_request.get(request_id)
        if planned_positive_phrase and planned_positive_phrase in serialized:
            actual_positive_requests.add(request_id)
            actual_positive_observation_ids.append(obs["observation_id"])
            actual_positive_family_counter.update([planned_positive_family_by_request.get(request_id, "unknown")])
        if planned_negative_phrase and planned_negative_phrase in serialized:
            actual_negative_requests.add(request_id)
            actual_negative_observation_ids.append(obs["observation_id"])
            actual_negative_family_counter.update([planned_negative_family_by_request.get(request_id, "unknown")])

    total_generation_rows = len(raw_calls)
    trace_tool_distribution = Counter()
    tool_count_per_trace = Counter()
    trace_observation_counts = Counter()
    for obs in tool_rows:
        tool_count_per_trace[obs["trace_id"]] += 1
    for obs in observations:
        trace_observation_counts[obs["trace_id"]] += 1
    for count in tool_count_per_trace.values():
        trace_tool_distribution[count] += 1
    text_reuse_summary = build_text_reuse_summary(observations)

    return {
        "generation_rows": total_generation_rows,
        "top_level_observation_rows": len(top_level_rows),
        "observation_rows": len(observations),
        "trace_count": len(trace_generation_counts),
        "tenant_count": len(tenant_counter),
        "app_count": len(app_counter),
        "request_path_counts": dict(request_path_counter),
        "tenant_distribution": dict(tenant_counter),
        "app_distribution": dict(app_counter),
        "model_distribution": dict(model_counter),
        "source_distribution": dict(source_counter),
        "trace_archetype_counts": dict(trace_archetype_trace_counts),
        "trace_archetype_generation_counts": dict(archetype_counter),
        "trace_archetype_trace_counts": dict(trace_archetype_trace_counts),
        "request_kind_counts": dict(request_kind_counter),
        "language_distribution": dict(language_counter),
        "messages_body_size_buckets": dict(message_bucket_counter),
        "count_tokens_body_size_buckets": dict(count_bucket_counter),
        "messages_len": quantiles(message_lengths),
        "tools_len": quantiles(tool_lengths),
        "observation_type_counts": dict(obs_type_counter),
        "observation_status_counts": dict(obs_status_counter),
        "observation_type_ratios": {
            key: round(value / max(1, len(observations)), 3) for key, value in obs_type_counter.items()
        },
        "trace_generation_distribution": dict(Counter(trace_generation_counts.values())),
        "trace_observation_distribution": dict(Counter(trace_observation_counts.values())),
        "trace_tool_count_distribution": dict(trace_tool_distribution),
        "failure_rates": {
            "trace_failure_rate": round(sum(1 for status in trace_status.values() if status == "failed") / max(1, len(trace_generation_counts)), 3),
            "tool_failure_rate": round(sum(1 for obs in tool_rows if obs["status"] == "error") / max(1, len(tool_rows)), 3),
            "retry_trace_rate": round(sum(1 for raw in raw_calls if raw["v"]["trace_archetype"] == "retry_after_429") / max(1, total_generation_rows), 3),
            "guardrail_trace_rate": round(sum(1 for raw in raw_calls if raw["v"]["trace_archetype"] == "guardrail_block") / max(1, total_generation_rows), 3),
            "timeout_trace_rate": round(sum(1 for raw in raw_calls if raw["v"]["trace_archetype"] == "timeout_then_fallback") / max(1, total_generation_rows), 3),
        },
        "keyword_injection": {
            "strong_rate": round(len(actual_positive_requests) / max(1, total_generation_rows), 3),
            "hard_negative_rate": round(len(actual_negative_requests) / max(1, total_generation_rows), 3),
            "positive_families": dict(actual_positive_family_counter),
            "negative_families": dict(actual_negative_family_counter),
            "planned_positive_families": dict(strong_labels),
            "planned_negative_families": dict(negative_labels),
            "positive_observation_ids": actual_positive_observation_ids[:24],
            "negative_observation_ids": actual_negative_observation_ids[:24],
        },
        "payload_coverage": {
            "generation": generation_attr_cov,
            "tool": tool_attr_cov,
            "attr": {
                "unique_key_count": len(attr_key_counter),
                "p50_keys_per_observation": sorted(attr_count_per_observation)[len(attr_count_per_observation) // 2] if attr_count_per_observation else 0,
                "max_keys_per_observation": max(attr_count_per_observation) if attr_count_per_observation else 0,
                "core_field_presence_ratio": {
                    key: round(attr_presence_counter[key] / max(1, len(observations)), 3)
                    for key in DYNAMIC_CORE_FIELD_POOLS
                },
                "top_keys": dict(attr_key_counter.most_common(20)),
            },
        },
        "telemetry_coverage": {
            key: round(telemetry_counter[key] / max(1, len(observations)), 3)
            for key in ("resource", "scope", "otel", "langfuse", "mlflow")
        },
        "text_reuse": text_reuse_summary,
        "tool_name_distribution": dict(tool_name_counter),
        "error_text_distribution": dict(error_text_distribution),
    }


def make_accuracy_labels(
    observations: List[Dict[str, Any]],
    summary: Dict[str, Any],
    replay_observation_id: str,
) -> Dict[str, Any]:
    keyword_observation_ids = summary["keyword_injection"].get("positive_observation_ids", [])
    return {
        "version": 2,
        "replay_observation_id": replay_observation_id,
        "keyword_observation_ids": keyword_observation_ids[:10],
        "top_models": [
            item[0]
            for item in sorted(summary["model_distribution"].items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        ],
    }


def generate_dataset_chunk(
    output_dir: Path,
    seed_dir: Path,
    generation_target: int,
    trace_target: int,
    seed: int,
    call_idx_start: int = 1,
    trace_idx_start: int = 1,
    edition: str = "2026.04-observability-v1-small",
    observation_file: str = "agent_observations_s.ndjson",
) -> GeneratedDataset:
    rng = random.Random(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    seed_material = load_seed_material(seed_dir)

    tenants = make_long_tail_pool("tenant", TENANT_COUNT_SMALL)
    apps = make_long_tail_pool("app", APP_COUNT_SMALL)
    tenant_weights = make_long_tail_weights(TENANT_COUNT_SMALL)
    app_weights = make_long_tail_weights(APP_COUNT_SMALL)
    huge_remaining = [1]
    day_hot_tenants: Dict[int, List[str]] = {}
    day_hot_apps: Dict[int, List[str]] = {}

    strong_target = max(1, round(generation_target * 0.18))
    negative_target = max(strong_target, round(strong_target * 1.2))
    strong_queue = []
    negative_queue = []
    for family, phrases in POSITIVE_PHRASES.items():
        strong_queue.extend((family, phrase) for phrase in phrases)
    for family, phrases in NEGATIVE_PHRASES.items():
        negative_queue.extend((family, phrase) for phrase in phrases)
    rng.shuffle(strong_queue)
    rng.shuffle(negative_queue)

    raw_calls: List[Dict[str, Any]] = []
    base_date = datetime(2026, 3, 17, tzinfo=timezone.utc)
    call_idx = call_idx_start
    trace_idx = trace_idx_start
    seen_apps = set()
    seen_tenants = set()
    strong_family_counter = Counter()
    negative_family_counter = Counter()

    trace_call_counts = plan_generation_counts(rng, trace_target, generation_target)

    for planned_calls in trace_call_counts:
        trace_id = deterministic_uuid("trace", trace_idx)
        session_id = deterministic_uuid("sess", trace_idx)
        trace_sequence = max(0, trace_idx - trace_idx_start)
        day_index = trace_sequence % 5
        calendar_day_offset = (trace_sequence // 5) % 365
        minute_offset = (trace_sequence * 13) % 60
        hot_tenants = day_hot_tenants.setdefault(day_index, rng.sample(tenants, k=min(4, len(tenants))))
        hot_apps = day_hot_apps.setdefault(day_index, rng.sample(apps, k=min(6, len(apps))))
        tenant = choose_hotspot_entity(rng, tenants, tenant_weights, hot_tenants, seen_tenants, 10)
        seen_tenants.add(tenant)
        app = choose_hotspot_entity(rng, apps, app_weights, hot_apps, seen_apps, 12)
        seen_apps.add(app)
        archetype = weighted_choice(rng, ARCHETYPE_WEIGHTS)
        category = weighted_choice(rng, TASK_CATEGORY_WEIGHTS)
        trace_start = base_date + timedelta(
            days=calendar_day_offset + day_index,
            hours=choose_hour(rng),
            minutes=minute_offset,
        )
        elapsed_minutes = 0
        for _ in range(planned_calls):
            request_kind = weighted_choice(rng, REQUEST_KIND_WEIGHTS)
            request_path = "/v1/messages/count_tokens" if request_kind == "count_tokens" else "/v1/messages"
            model = weighted_choice(rng, MODEL_WEIGHTS)
            elapsed_minutes += rng.randint(2, 19)
            timestamp = trace_start + timedelta(minutes=elapsed_minutes)
            text_profile = choose_text_profile(rng)
            positive_phrase = strong_queue[len(raw_calls)] if len(raw_calls) < strong_target and len(raw_calls) < len(strong_queue) else None
            negative_phrase = negative_queue[len(raw_calls)] if len(raw_calls) < negative_target and len(raw_calls) < len(negative_queue) else None
            pos_text = positive_phrase[1] if positive_phrase else None
            neg_text = negative_phrase[1] if negative_phrase else None
            if request_path == "/v1/messages":
                raw = build_messages_call(
                    seed_material,
                    rng,
                    call_idx,
                    trace_id,
                    session_id,
                    timestamp,
                    tenant,
                    app,
                    model,
                    archetype,
                    request_kind,
                    category,
                    text_profile,
                    pos_text,
                    neg_text,
                    huge_remaining,
                )
            else:
                raw = build_count_tokens_call(
                    seed_material,
                    rng,
                    call_idx,
                    trace_id,
                    session_id,
                    timestamp,
                    tenant,
                    app,
                    model,
                    archetype,
                    category,
                    text_profile,
                    pos_text,
                    neg_text,
                    huge_remaining,
                )
            raw["v"]["benchmark_labels"] = {
                "positive_phrase": pos_text,
                "negative_phrase": neg_text,
                "positive_family": positive_phrase[0] if positive_phrase else None,
                "negative_family": negative_phrase[0] if negative_phrase else None,
            }
            if positive_phrase:
                strong_family_counter[positive_phrase[0]] += 1
            if negative_phrase:
                negative_family_counter[negative_phrase[0]] += 1
            raw_calls.append(raw)
            call_idx += 1
        trace_idx += 1

    observations, tool_name_counter = compile_observations(raw_calls)
    summary = build_summary(raw_calls, observations, tool_name_counter, strong_family_counter, negative_family_counter)
    failure_trace_ids = {
        obs["trace_id"]
        for obs in observations
        if obs["type"] == "TOOL" and obs["status"] == "error"
    }
    replay_generation = next(
        (
            obs
            for obs in observations
            if obs["type"] == "GENERATION" and obs["trace_id"] in failure_trace_ids
        ),
        next(obs for obs in observations if obs["type"] == "GENERATION"),
    )
    accuracy_labels = make_accuracy_labels(observations, summary, replay_generation["observation_id"])
    manifest = {
        "edition": edition,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "seed": seed,
        "seed_files": sorted(str(path.relative_to(seed_dir)) for path in seed_dir.rglob("*.json")),
        "trace_target": trace_target,
        "generation_target": generation_target,
        "observation_file": observation_file,
        "summary_file": "summary.json",
        "accuracy_labels_file": "accuracy_labels.json",
        "replay_trace_id": replay_generation["trace_id"],
        "replay_observation_id": replay_generation["observation_id"],
    }
    return GeneratedDataset(raw_calls, observations, summary, accuracy_labels, manifest)


def generate_large_dataset_shard(
    output_dir: Path,
    seed_dir: Path,
    generation_target: int,
    trace_target: int,
    seed: int,
    observation_path: Path,
    call_idx_start: int = 1,
    trace_idx_start: int = 1,
    edition: str = "2026.04-observability-v1-large",
) -> GeneratedShard:
    rng = random.Random(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    seed_material = load_seed_material(seed_dir)

    tenants = make_long_tail_pool("tenant", TENANT_COUNT_SMALL)
    apps = make_long_tail_pool("app", APP_COUNT_SMALL)
    tenant_weights = make_long_tail_weights(TENANT_COUNT_SMALL)
    app_weights = make_long_tail_weights(APP_COUNT_SMALL)
    huge_remaining = [1]
    day_hot_tenants: Dict[int, List[str]] = {}
    day_hot_apps: Dict[int, List[str]] = {}

    strong_target = max(1, round(generation_target * 0.18))
    negative_target = max(strong_target, round(strong_target * 1.2))
    strong_queue = []
    negative_queue = []
    for family, phrases in POSITIVE_PHRASES.items():
        strong_queue.extend((family, phrase) for phrase in phrases)
    for family, phrases in NEGATIVE_PHRASES.items():
        negative_queue.extend((family, phrase) for phrase in phrases)
    rng.shuffle(strong_queue)
    rng.shuffle(negative_queue)

    call_idx = call_idx_start
    trace_idx = trace_idx_start
    seen_apps = set()
    seen_tenants = set()
    seq_counter: Dict[str, int] = defaultdict(int)
    source_counter = Counter()
    model_counter = Counter()
    tool_name_counter = Counter()
    observation_rows = 0
    first_generation: Dict[str, str] | None = None
    replay_generation: Dict[str, str] | None = None
    base_date = datetime(2026, 3, 17, tzinfo=timezone.utc)

    trace_call_counts = plan_generation_counts(rng, trace_target, generation_target)

    with observation_path.open("w", encoding="utf-8") as handle:
        for planned_calls in trace_call_counts:
            trace_id = deterministic_uuid("trace", trace_idx)
            session_id = deterministic_uuid("sess", trace_idx)
            trace_sequence = max(0, trace_idx - trace_idx_start)
            day_index = trace_sequence % 5
            calendar_day_offset = (trace_sequence // 5) % 365
            minute_offset = (trace_sequence * 13) % 60
            hot_tenants = day_hot_tenants.setdefault(day_index, rng.sample(tenants, k=min(4, len(tenants))))
            hot_apps = day_hot_apps.setdefault(day_index, rng.sample(apps, k=min(6, len(apps))))
            tenant = choose_hotspot_entity(rng, tenants, tenant_weights, hot_tenants, seen_tenants, 10)
            seen_tenants.add(tenant)
            app = choose_hotspot_entity(rng, apps, app_weights, hot_apps, seen_apps, 12)
            seen_apps.add(app)
            archetype = weighted_choice(rng, ARCHETYPE_WEIGHTS)
            category = weighted_choice(rng, TASK_CATEGORY_WEIGHTS)
            trace_start = base_date + timedelta(
                days=calendar_day_offset + day_index,
                hours=choose_hour(rng),
                minutes=minute_offset,
            )
            elapsed_minutes = 0
            for _ in range(planned_calls):
                request_kind = weighted_choice(rng, REQUEST_KIND_WEIGHTS)
                request_path = "/v1/messages/count_tokens" if request_kind == "count_tokens" else "/v1/messages"
                model = weighted_choice(rng, MODEL_WEIGHTS)
                elapsed_minutes += rng.randint(2, 19)
                timestamp = trace_start + timedelta(minutes=elapsed_minutes)
                text_profile = choose_text_profile(rng)
                queue_index = call_idx - call_idx_start
                positive_phrase = (
                    strong_queue[queue_index]
                    if queue_index < strong_target and queue_index < len(strong_queue)
                    else None
                )
                negative_phrase = (
                    negative_queue[queue_index]
                    if queue_index < negative_target and queue_index < len(negative_queue)
                    else None
                )
                pos_text = positive_phrase[1] if positive_phrase else None
                neg_text = negative_phrase[1] if negative_phrase else None
                if request_path == "/v1/messages":
                    raw = build_messages_call(
                        seed_material,
                        rng,
                        call_idx,
                        trace_id,
                        session_id,
                        timestamp,
                        tenant,
                        app,
                        model,
                        archetype,
                        request_kind,
                        category,
                        text_profile,
                        pos_text,
                        neg_text,
                        huge_remaining,
                    )
                else:
                    raw = build_count_tokens_call(
                        seed_material,
                        rng,
                        call_idx,
                        trace_id,
                        session_id,
                        timestamp,
                        tenant,
                        app,
                        model,
                        archetype,
                        category,
                        text_profile,
                        pos_text,
                        neg_text,
                        huge_remaining,
                    )
                raw["v"]["benchmark_labels"] = {
                    "positive_phrase": pos_text,
                    "negative_phrase": neg_text,
                    "positive_family": positive_phrase[0] if positive_phrase else None,
                    "negative_family": negative_phrase[0] if negative_phrase else None,
                }
                source_counter.update([raw["source"]])
                model_counter.update([raw["model"]])
                row_observations, row_tool_names, generation_id, has_tool_error = build_observations_for_raw(
                    raw,
                    seq_counter,
                )
                tool_name_counter.update(row_tool_names)
                if raw["request_path"] == "/v1/messages":
                    generation_ref = {"trace_id": trace_id, "observation_id": generation_id}
                    first_generation = first_generation or generation_ref
                    if has_tool_error and replay_generation is None:
                        replay_generation = generation_ref
                for observation in row_observations:
                    handle.write(json.dumps(observation, ensure_ascii=False, separators=(",", ":")) + "\n")
                    observation_rows += 1
                call_idx += 1
            trace_idx += 1

    replay_generation = replay_generation or first_generation
    if replay_generation is None:
        raise RuntimeError("large shard generation did not produce any generation observations")

    summary = {
        "generation_rows": generation_target,
        "observation_rows": observation_rows,
        "trace_count": trace_target,
        "source_distribution": dict(source_counter),
        "model_distribution": dict(model_counter),
        "tool_name_distribution": dict(tool_name_counter),
    }
    accuracy_labels = {
        "version": 1,
        "replay_observation_id": replay_generation["observation_id"],
        "top_models": [item[0] for item in model_counter.most_common(5)],
    }
    manifest = {
        "edition": edition,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "seed": seed,
        "seed_files": sorted(str(path.relative_to(seed_dir)) for path in seed_dir.rglob("*.json")),
        "trace_target": trace_target,
        "generation_target": generation_target,
        "observation_file": observation_path.name,
        "summary_file": "summary.json",
        "accuracy_labels_file": "accuracy_labels.json",
        "replay_trace_id": replay_generation["trace_id"],
        "replay_observation_id": replay_generation["observation_id"],
    }
    return GeneratedShard(summary=summary, accuracy_labels=accuracy_labels, manifest=manifest)


def generate_small_dataset(
    output_dir: Path,
    seed_dir: Path,
    generation_target: int = 48,
    trace_target: int = 20,
    seed: int = 20260411,
) -> GeneratedDataset:
    return generate_dataset_chunk(
        output_dir=output_dir,
        seed_dir=seed_dir,
        generation_target=generation_target,
        trace_target=trace_target,
        seed=seed,
        call_idx_start=1,
        trace_idx_start=1,
        edition="2026.04-observability-v1-small",
        observation_file="agent_observations_s.ndjson",
    )


def write_ndjson(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_dataset(dataset: GeneratedDataset, output_dir: Path) -> None:
    legacy_raw_file = output_dir / "raw_agent_calls_s.ndjson"
    if legacy_raw_file.exists():
        legacy_raw_file.unlink()
    write_ndjson(output_dir / "agent_observations_s.ndjson", dataset.observations)
    (output_dir / "summary.json").write_text(json.dumps(dataset.summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "accuracy_labels.json").write_text(json.dumps(dataset.accuracy_labels, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "manifest.json").write_text(json.dumps(dataset.manifest, ensure_ascii=False, indent=2), encoding="utf-8")
