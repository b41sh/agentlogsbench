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
FROM agent_observations
WHERE biz_date BETWEEN DATE '__START_DATE__' AND DATE '__END_DATE__'
  AND tenant = '__TENANT__'
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
FROM agent_observations
WHERE biz_date BETWEEN DATE '__START_DATE__' AND DATE '__END_DATE__'
GROUP BY trace_id
ORDER BY total_cost DESC, total_latency_ms DESC, trace_id ASC
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
FROM agent_observations
WHERE trace_id = '__TRACE_ID__'
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
FROM agent_observations AS child
LEFT JOIN agent_observations AS parent
  ON child.parent_observation_id = parent.observation_id
WHERE child.trace_id = '__TRACE_ID__'
ORDER BY child.seq_no ASC;

-- Q05
SELECT
  event_time,
  trace_id,
  observation_id,
  tool_name,
  latency_ms,
  (
    CASE WHEN contains(lower(concat_ws(' ', coalesce(input, ''), coalesce(output, ''))), 'unable') THEN 1 ELSE 0 END +
    CASE WHEN contains(lower(concat_ws(' ', coalesce(input, ''), coalesce(output, ''))), 'open') THEN 1 ELSE 0 END
  ) AS text_score,
  payload
FROM agent_observations
WHERE type = 'TOOL'
  AND status = 'error'
  AND tenant = '__TENANT__'
  AND app = '__APP__'
  AND contains(lower(concat_ws(' ', coalesce(input, ''), coalesce(output, ''))), 'unable')
  AND contains(lower(concat_ws(' ', coalesce(input, ''), coalesce(output, ''))), 'open')
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
FROM agent_observations
GROUP BY type, model
ORDER BY total_cost DESC, avg_latency_ms DESC,
  observations DESC, input_tokens DESC, output_tokens DESC,
  type ASC, model ASC
LIMIT 50;

-- Q07
SELECT
  event_time,
  trace_id,
  observation_id,
  type,
  status,
  payload
FROM agent_observations
WHERE environment = 'prod'
  AND type IN ('GENERATION', 'TOOL', 'RETRIEVAL')
  AND payload.attr.release_ring IN ('stable', 'canary')
  AND payload.attr.retrieval_strategy IN ('hybrid', 'hybrid_rerank')
  AND payload.attr.surface IN ('api', 'workflow_runner')
  AND payload.attr.prompt_template_version IN ('pt_2026_03_2', 'pt_2026_04_1', 'pt_2026_04_2')
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
  contains(lower(concat_ws(' ', coalesce(input, ''), coalesce(output, ''))), 'unable to open') AS phrase_match,
  (
    CASE WHEN contains(lower(concat_ws(' ', coalesce(input, ''), coalesce(output, ''))), 'unable') THEN 1 ELSE 0 END +
    CASE WHEN contains(lower(concat_ws(' ', coalesce(input, ''), coalesce(output, ''))), 'open') THEN 1 ELSE 0 END
  ) AS text_score
FROM agent_observations
WHERE tenant = '__TENANT__'
  AND contains(lower(concat_ws(' ', coalesce(input, ''), coalesce(output, ''))), 'unable')
  AND contains(lower(concat_ws(' ', coalesce(input, ''), coalesce(output, ''))), 'open')
ORDER BY phrase_match DESC, text_score DESC, event_time DESC, trace_id DESC, observation_id DESC
LIMIT 50;

-- Q09
SELECT
  tool_name,
  status,
  count(*) AS observations,
  avg(latency_ms) AS avg_latency_ms
FROM agent_observations
WHERE type = 'TOOL'
GROUP BY tool_name, status
ORDER BY observations DESC, avg_latency_ms DESC, tool_name ASC, status ASC
LIMIT 50;

-- Q10
SELECT
  payload.provider.stop_reason AS stop_reason,
  payload.provider.cache_hit AS cache_hit,
  count(*) AS observations,
  avg(latency_ms) AS avg_latency_ms
FROM agent_observations
WHERE type = 'GENERATION'
GROUP BY 1, 2
ORDER BY observations DESC, avg_latency_ms DESC, stop_reason ASC, cache_hit ASC
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
  contains(lower(concat_ws(' ', coalesce(input, ''), coalesce(output, ''))), 'unable to open') AS phrase_match,
  (
    CASE WHEN contains(lower(concat_ws(' ', coalesce(input, ''), coalesce(output, ''))), 'unable') THEN 1 ELSE 0 END +
    CASE WHEN contains(lower(concat_ws(' ', coalesce(input, ''), coalesce(output, ''))), 'open') THEN 1 ELSE 0 END
  ) AS text_score
FROM agent_observations
WHERE tenant = '__TENANT__'
  AND app = '__APP__'
  AND type IN ('GENERATION', 'TOOL', 'RETRIEVAL')
  AND contains(lower(concat_ws(' ', coalesce(input, ''), coalesce(output, ''))), 'unable')
  AND contains(lower(concat_ws(' ', coalesce(input, ''), coalesce(output, ''))), 'open')
  AND contains(lower(concat_ws(' ', coalesce(input, ''), coalesce(output, ''))), 'unable to open')
ORDER BY phrase_match DESC, text_score DESC, latency_ms DESC, event_time DESC, trace_id DESC, observation_id DESC
LIMIT 50;

-- Q12
SELECT
  payload.attr.release_ring AS release_ring,
  payload.attr.customer_tier AS customer_tier,
  payload.attr.retrieval_strategy AS retrieval_strategy,
  count(*) AS observations,
  avg(latency_ms) AS avg_latency_ms,
  sum(total_cost) AS total_cost
FROM agent_observations
GROUP BY 1, 2, 3
ORDER BY observations DESC, total_cost DESC,
  release_ring ASC, customer_tier ASC, retrieval_strategy ASC
LIMIT 50;

-- Q13
SELECT
  count(*) AS observations,
  count(DISTINCT trace_id) AS traces,
  max(event_time) AS last_event_time
FROM agent_observations
WHERE biz_date BETWEEN DATE '__START_DATE__' AND DATE '__END_DATE__'
  AND tenant = '__TENANT__'
  AND type IN ('GENERATION', 'TOOL', 'RETRIEVAL', 'EVENT')
  AND (
    contains(lower(concat_ws(' ', coalesce(input, ''), coalesce(output, ''))), 'timeout awaiting headers')
    OR contains(lower(concat_ws(' ', coalesce(input, ''), coalesce(output, ''))), 'retry budget depleted')
    OR contains(lower(concat_ws(' ', coalesce(input, ''), coalesce(output, ''))), 'transient upstream failure')
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
FROM agent_observations
WHERE tenant = '__TENANT__'
  AND app = '__APP__'
  AND type IN ('GENERATION', 'TOOL', 'EVENT')
  AND (
    lower(coalesce(input, '')) LIKE '%deployment%'
    OR lower(coalesce(output, '')) LIKE '%deployment%'
    OR lower(coalesce(input, '')) LIKE '%rollback%'
    OR lower(coalesce(output, '')) LIKE '%rollback%'
    OR lower(coalesce(output, '')) LIKE '%transient%'
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
FROM agent_observations
WHERE tenant = '__TENANT__'
  AND type IN ('GENERATION', 'TOOL', 'RETRIEVAL', 'EVENT')
  AND (
    contains(lower(concat_ws(' ', coalesce(input, ''), coalesce(output, ''))), 'transient upstream failure')
    OR contains(lower(concat_ws(' ', coalesce(input, ''), coalesce(output, ''))), 'retry budget depleted')
    OR contains(lower(concat_ws(' ', coalesce(input, ''), coalesce(output, ''))), 'connector timeout')
  )
ORDER BY latency_ms DESC, event_time DESC, trace_id DESC, observation_id DESC
LIMIT 50;

-- Q16
SELECT
  event_time,
  trace_id,
  observation_id,
  type,
  status,
  payload.attr.release_ring AS release_ring,
  payload.attr.customer_tier AS customer_tier,
  payload.attr.traffic_cluster AS traffic_cluster
FROM agent_observations
WHERE tenant = '__TENANT__'
  AND environment = 'prod'
  AND type IN ('GENERATION', 'TOOL', 'RETRIEVAL')
  AND payload.attr.release_ring = '__RELEASE_RING__'
  AND payload.attr.customer_tier = '__CUSTOMER_TIER__'
  AND payload.attr.traffic_cluster = '__TRAFFIC_CLUSTER__'
ORDER BY event_time DESC, trace_id DESC, observation_id DESC
LIMIT 50;

-- Q17
SELECT
  trace_id,
  observation_id,
  seq_no,
  type,
  status,
  payload.attr.request_key AS request_key,
  payload.attr.workflow_variant AS workflow_variant
FROM agent_observations
WHERE tenant = '__TENANT__'
  AND payload.attr.request_key = '__REQUEST_KEY__'
  AND payload.attr.workflow_variant = '__WORKFLOW_VARIANT__'
ORDER BY seq_no ASC, observation_id ASC
LIMIT 100;

-- Q18
SELECT
  payload.attr.prompt_template_version AS prompt_template_version,
  count(*) AS observations,
  count(DISTINCT trace_id) AS traces,
  avg(latency_ms) AS avg_latency_ms,
  sum(total_cost) AS total_cost
FROM agent_observations
WHERE type IN ('GENERATION', 'REASONING', 'TOOL')
GROUP BY 1
ORDER BY observations DESC, total_cost DESC, prompt_template_version ASC
LIMIT 20;

-- Q19
SELECT
  payload.attr.deployment_channel AS deployment_channel,
  payload.attr.release_ring AS release_ring,
  count(*) AS incident_observations,
  count(DISTINCT trace_id) AS incident_traces,
  avg(latency_ms) AS avg_latency_ms
FROM agent_observations
WHERE type IN ('GENERATION', 'TOOL', 'RETRIEVAL', 'EVENT')
  AND (
    contains(lower(concat_ws(' ', coalesce(input, ''), coalesce(output, ''))), 'error')
    OR contains(lower(concat_ws(' ', coalesce(input, ''), coalesce(output, ''))), 'timeout')
    OR contains(lower(concat_ws(' ', coalesce(input, ''), coalesce(output, ''))), 'retry')
  )
GROUP BY 1, 2
ORDER BY incident_observations DESC, incident_traces DESC, deployment_channel ASC, release_ring ASC
LIMIT 20;

-- Q20
SELECT
  payload.attr.workflow_variant AS workflow_variant,
  payload.attr.policy_pack AS policy_pack,
  count(*) AS observations,
  count(DISTINCT tenant) AS tenants,
  avg(latency_ms) AS avg_latency_ms,
  sum(total_cost) AS total_cost
FROM agent_observations
WHERE type IN ('GENERATION', 'TOOL', 'RETRIEVAL', 'REASONING')
GROUP BY 1, 2
ORDER BY observations DESC, total_cost DESC, workflow_variant ASC, policy_pack ASC
LIMIT 20;
