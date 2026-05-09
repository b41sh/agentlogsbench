-- Q01
SELECT
  event_time,
  trace_id,
  observation_id,
  seq_no,
  type,
  status,
  model,
  tool_name,
  latency_ms
FROM bench.agent_observations
WHERE biz_date BETWEEN start_date_param AND end_date_param
  AND tenant = tenant_param
  AND type IN ('GENERATION', 'TOOL')
  AND status IN ('ok', 'error')
ORDER BY event_time DESC, seq_no DESC
LIMIT 50;

-- Q02
SELECT
  trace_id,
  min(event_time) AS started_at,
  count(*) AS observation_count,
  sum(CASE WHEN status <> 'ok' THEN 1 ELSE 0 END) AS failure_count,
  sum(total_cost) AS total_cost,
  sum(latency_ms) AS total_latency_ms
FROM bench.agent_observations
WHERE biz_date BETWEEN start_date_param AND end_date_param
GROUP BY trace_id
ORDER BY total_cost DESC, total_latency_ms DESC
  , trace_id ASC
LIMIT 50;

-- Q03
SELECT
  trace_id,
  seq_no,
  type,
  status,
  model,
  tool_name,
  input,
  output
FROM bench.agent_observations
WHERE trace_id = trace_id_param
ORDER BY seq_no ASC;

-- Q04
SELECT
  child.trace_id,
  child.seq_no,
  child.observation_id,
  child.parent_observation_id,
  NULLIF(parent.type, '') AS parent_type,
  child.type AS child_type,
  child.status,
  child.tool_name
FROM bench.agent_observations AS child
LEFT JOIN bench.agent_observations AS parent
  ON child.parent_observation_id = parent.observation_id
WHERE child.trace_id = trace_id_param
ORDER BY child.seq_no ASC;

-- Q05
SELECT
  event_time,
  trace_id,
  observation_id,
  tool_name,
  latency_ms,
  (
    toUInt8(
      hasTokenCaseInsensitive(
        lowerUTF8(concat(ifNull(input, ''), ' ', ifNull(output, ''))),
        'unable'
      )
    ) +
    toUInt8(
      hasTokenCaseInsensitive(
        lowerUTF8(concat(ifNull(input, ''), ' ', ifNull(output, ''))),
        'open'
      )
    )
  ) AS text_score,
  payload
FROM bench.agent_observations
WHERE type = 'TOOL'
  AND status = 'error'
  AND tenant = tenant_param
  AND app = app_param
  AND hasAllTokens(
    lowerUTF8(concat(ifNull(input, ''), ' ', ifNull(output, ''))),
    ['unable', 'open']
  )
ORDER BY text_score DESC, latency_ms DESC, event_time DESC
LIMIT 50;

-- Q06
SELECT
  type,
  model,
  count(*) AS observations,
  sum(input_tokens) AS input_tokens,
  sum(output_tokens) AS output_tokens,
  sum(total_cost) AS total_cost,
  avg(latency_ms) AS avg_latency_ms
FROM bench.agent_observations
GROUP BY type, model
ORDER BY total_cost DESC, avg_latency_ms DESC
  , observations DESC, input_tokens DESC, output_tokens DESC
  , type ASC, model ASC
LIMIT 50;

-- Q07
SELECT
  event_time,
  trace_id,
  observation_id,
  type,
  status,
  payload
FROM bench.agent_observations
WHERE environment = 'prod'
  AND type IN ('GENERATION', 'TOOL', 'RETRIEVAL')
  AND payload.attr.release_ring::String IN ('stable', 'canary')
  AND payload.attr.retrieval_strategy::String IN ('hybrid', 'hybrid_rerank')
  AND payload.attr.surface::String IN ('api', 'workflow_runner')
  AND payload.attr.prompt_template_version::String IN ('pt_2026_03_2', 'pt_2026_04_1', 'pt_2026_04_2')
ORDER BY event_time DESC, trace_id DESC, observation_id DESC
LIMIT 50;

-- Q08
SELECT
  event_time,
  trace_id,
  observation_id,
  type,
  status,
  input,
  output,
  toUInt8(
    positionCaseInsensitiveUTF8(
      lowerUTF8(concat(ifNull(input, ''), ' ', ifNull(output, ''))),
      'unable to open'
    ) > 0
  ) AS phrase_match,
  (
    toUInt8(
      hasTokenCaseInsensitive(
        lowerUTF8(concat(ifNull(input, ''), ' ', ifNull(output, ''))),
        'unable'
      )
    ) +
    toUInt8(
      hasTokenCaseInsensitive(
        lowerUTF8(concat(ifNull(input, ''), ' ', ifNull(output, ''))),
        'open'
      )
    )
  ) AS text_score
FROM bench.agent_observations
WHERE tenant = tenant_param
  AND hasAllTokens(
    lowerUTF8(concat(ifNull(input, ''), ' ', ifNull(output, ''))),
    ['unable', 'open']
  )
  AND positionCaseInsensitiveUTF8(
    lowerUTF8(concat(ifNull(input, ''), ' ', ifNull(output, ''))),
    'unable to open'
  ) > 0
ORDER BY phrase_match DESC, text_score DESC, event_time DESC, trace_id DESC, observation_id DESC
LIMIT 50
SETTINGS enable_full_text_index = 1, use_skip_indexes_on_data_read = 1, query_plan_direct_read_from_text_index = 1;

-- Q09
SELECT
  tool_name,
  status,
  count(*) AS observations,
  avg(latency_ms) AS avg_latency_ms
FROM bench.agent_observations
WHERE type = 'TOOL'
GROUP BY tool_name, status
ORDER BY observations DESC, avg_latency_ms DESC
  , tool_name ASC, status ASC
LIMIT 50;

-- Q10
SELECT
  payload.provider.stop_reason::String AS stop_reason,
  multiIf(ifNull(payload.provider.cache_hit::Bool, false), 'true', 'false') AS cache_hit,
  count(*) AS observations,
  avg(latency_ms) AS avg_latency_ms
FROM bench.agent_observations
WHERE type = 'GENERATION'
GROUP BY payload.provider.stop_reason::String, multiIf(ifNull(payload.provider.cache_hit::Bool, false), 'true', 'false')
ORDER BY observations DESC, avg_latency_ms DESC
  , stop_reason ASC, cache_hit ASC
LIMIT 50;

-- Q11
SELECT
  event_time,
  trace_id,
  observation_id,
  type,
  status,
  tool_name,
  latency_ms,
  toUInt8(
    positionCaseInsensitiveUTF8(
      lowerUTF8(concat(ifNull(input, ''), ' ', ifNull(output, ''))),
      'unable to open'
    ) > 0
  ) AS phrase_match,
  (
    toUInt8(
      hasTokenCaseInsensitive(
        lowerUTF8(concat(ifNull(input, ''), ' ', ifNull(output, ''))),
        'unable'
      )
    ) +
    toUInt8(
      hasTokenCaseInsensitive(
        lowerUTF8(concat(ifNull(input, ''), ' ', ifNull(output, ''))),
        'open'
      )
    )
  ) AS text_score
FROM bench.agent_observations
WHERE tenant = tenant_param
  AND app = app_param
  AND type IN ('GENERATION', 'TOOL', 'RETRIEVAL')
  AND hasAllTokens(
    lowerUTF8(concat(ifNull(input, ''), ' ', ifNull(output, ''))),
    ['unable', 'open']
  )
  AND positionCaseInsensitiveUTF8(
    lowerUTF8(concat(ifNull(input, ''), ' ', ifNull(output, ''))),
    'unable to open'
  ) > 0
ORDER BY phrase_match DESC, text_score DESC, latency_ms DESC, event_time DESC, trace_id DESC, observation_id DESC
LIMIT 50
SETTINGS enable_full_text_index = 1, use_skip_indexes_on_data_read = 1, query_plan_direct_read_from_text_index = 1;

-- Q12
SELECT
  payload.attr.release_ring::String AS release_ring,
  payload.attr.customer_tier::String AS customer_tier,
  payload.attr.retrieval_strategy::String AS retrieval_strategy,
  count(*) AS observations,
  avg(latency_ms) AS avg_latency_ms,
  sum(total_cost) AS total_cost
FROM bench.agent_observations
WHERE type IN ('GENERATION', 'TOOL', 'RETRIEVAL')
GROUP BY
  payload.attr.release_ring::String,
  payload.attr.customer_tier::String,
  payload.attr.retrieval_strategy::String
ORDER BY observations DESC, total_cost DESC
  , release_ring ASC, customer_tier ASC, retrieval_strategy ASC
LIMIT 50;

-- Q13
SELECT
  count() AS observations,
  uniqExact(trace_id) AS traces,
  max(event_time) AS last_event_time
FROM bench.agent_observations
WHERE biz_date BETWEEN start_date_param AND end_date_param
  AND tenant = tenant_param
  AND type IN ('GENERATION', 'TOOL', 'RETRIEVAL', 'EVENT')
  AND (
    positionCaseInsensitiveUTF8(
      lowerUTF8(concat(ifNull(input, ''), ' ', ifNull(output, ''))),
      'timeout awaiting headers'
    ) > 0
    OR positionCaseInsensitiveUTF8(
      lowerUTF8(concat(ifNull(input, ''), ' ', ifNull(output, ''))),
      'retry budget depleted'
    ) > 0
    OR positionCaseInsensitiveUTF8(
      lowerUTF8(concat(ifNull(input, ''), ' ', ifNull(output, ''))),
      'transient upstream failure'
    ) > 0
  );

-- Q14
SELECT
  event_time,
  trace_id,
  observation_id,
  type,
  status,
  tool_name,
  output
FROM bench.agent_observations
WHERE tenant = tenant_param
  AND app = app_param
  AND type IN ('GENERATION', 'TOOL', 'EVENT')
  AND (
    lowerUTF8(ifNull(input, '')) LIKE '%deployment%'
    OR lowerUTF8(ifNull(output, '')) LIKE '%deployment%'
    OR lowerUTF8(ifNull(input, '')) LIKE '%rollback%'
    OR lowerUTF8(ifNull(output, '')) LIKE '%rollback%'
    OR lowerUTF8(ifNull(output, '')) LIKE '%transient%'
  )
ORDER BY event_time DESC, trace_id DESC, observation_id DESC
LIMIT 50;

-- Q15
SELECT
  event_time,
  trace_id,
  observation_id,
  type,
  status,
  tool_name,
  latency_ms
FROM bench.agent_observations
WHERE tenant = tenant_param
  AND type IN ('GENERATION', 'TOOL', 'RETRIEVAL', 'EVENT')
  AND (
    positionCaseInsensitiveUTF8(
      lowerUTF8(concat(ifNull(input, ''), ' ', ifNull(output, ''))),
      'transient upstream failure'
    ) > 0
    OR positionCaseInsensitiveUTF8(
      lowerUTF8(concat(ifNull(input, ''), ' ', ifNull(output, ''))),
      'retry budget depleted'
    ) > 0
    OR positionCaseInsensitiveUTF8(
      lowerUTF8(concat(ifNull(input, ''), ' ', ifNull(output, ''))),
      'connector timeout'
    ) > 0
  )
ORDER BY latency_ms DESC, event_time DESC, trace_id DESC, observation_id DESC
LIMIT 50
SETTINGS enable_full_text_index = 1, use_skip_indexes_on_data_read = 1, query_plan_direct_read_from_text_index = 1;

-- Q16
SELECT
  event_time,
  trace_id,
  observation_id,
  type,
  status,
  payload.attr.release_ring::String AS release_ring,
  payload.attr.customer_tier::String AS customer_tier,
  payload.attr.traffic_cluster::String AS traffic_cluster
FROM bench.agent_observations
WHERE tenant = tenant_param
  AND environment = 'prod'
  AND type IN ('GENERATION', 'TOOL', 'RETRIEVAL')
  AND payload.attr.release_ring::String = release_ring_param
  AND payload.attr.customer_tier::String = customer_tier_param
  AND payload.attr.traffic_cluster::String = traffic_cluster_param
ORDER BY event_time DESC, trace_id DESC, observation_id DESC
LIMIT 50;

-- Q17
SELECT
  trace_id,
  observation_id,
  seq_no,
  type,
  status,
  payload.attr.request_key::String AS request_key,
  payload.attr.workflow_variant::String AS workflow_variant
FROM bench.agent_observations
WHERE tenant = tenant_param
  AND payload.attr.request_key::String = request_key_param
  AND payload.attr.workflow_variant::String = workflow_variant_param
ORDER BY seq_no ASC, observation_id ASC
LIMIT 100;

-- Q18
SELECT
  payload.attr.prompt_template_version::String AS prompt_template_version,
  count() AS observations,
  uniqExact(trace_id) AS traces,
  avg(latency_ms) AS avg_latency_ms,
  sum(total_cost) AS total_cost
FROM bench.agent_observations
WHERE type IN ('GENERATION', 'REASONING', 'TOOL')
GROUP BY payload.attr.prompt_template_version::String
ORDER BY observations DESC, total_cost DESC, prompt_template_version ASC
LIMIT 20;

-- Q19
SELECT
  payload.attr.deployment_channel::String AS deployment_channel,
  payload.attr.release_ring::String AS release_ring,
  count() AS incident_observations,
  uniqExact(trace_id) AS incident_traces,
  avg(latency_ms) AS avg_latency_ms
FROM bench.agent_observations
WHERE type IN ('GENERATION', 'TOOL', 'RETRIEVAL', 'EVENT')
  AND match(
    lowerUTF8(concat(ifNull(input, ''), ' ', ifNull(output, ''))),
    '(^|[^a-z])(error|timeout|retry)([^a-z]|$)'
  )
GROUP BY deployment_channel, release_ring
ORDER BY incident_observations DESC, incident_traces DESC, deployment_channel ASC, release_ring ASC
LIMIT 20;

-- Q20
SELECT
  payload.attr.workflow_variant::String AS workflow_variant,
  payload.attr.policy_pack::String AS policy_pack,
  count() AS observations,
  uniqExact(tenant) AS tenants,
  avg(latency_ms) AS avg_latency_ms,
  sum(total_cost) AS total_cost
FROM bench.agent_observations
WHERE type IN ('GENERATION', 'TOOL', 'RETRIEVAL', 'REASONING')
GROUP BY payload.attr.workflow_variant::String, payload.attr.policy_pack::String
ORDER BY observations DESC, total_cost DESC, workflow_variant ASC, policy_pack ASC
LIMIT 20;
