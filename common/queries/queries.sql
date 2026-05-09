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
WHERE biz_date BETWEEN CAST(:start_date AS DATE) AND CAST(:end_date AS DATE)
  AND tenant = :tenant
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
WHERE biz_date BETWEEN CAST(:start_date AS DATE) AND CAST(:end_date AS DATE)
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
FROM agent_observations
WHERE trace_id = :trace_id
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
WHERE child.trace_id = :trace_id
ORDER BY child.seq_no ASC;

-- Q05
SELECT
  event_time,
  trace_id,
  observation_id,
  tool_name,
  latency_ms,
  (
    TEXT_TOKEN_SCORE(input, output, 'unable') +
    TEXT_TOKEN_SCORE(input, output, 'open')
  ) AS text_score,
  payload
FROM agent_observations
WHERE type = 'TOOL'
  AND status = 'error'
  AND tenant = :tenant
  AND app = :app
  AND TEXT_HAS_TOKEN(input, output, 'unable')
  AND TEXT_HAS_TOKEN(input, output, 'open')
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
FROM agent_observations
WHERE environment = 'prod'
  AND type IN ('GENERATION', 'TOOL', 'RETRIEVAL')
  AND JSON_VALUE(payload, '$.attr.release_ring') IN ('stable', 'canary')
  AND JSON_VALUE(payload, '$.attr.retrieval_strategy') IN ('hybrid', 'hybrid_rerank')
  AND JSON_VALUE(payload, '$.attr.surface') IN ('api', 'workflow_runner')
  AND JSON_VALUE(payload, '$.attr.prompt_template_version') IN ('pt_2026_03_2', 'pt_2026_04_1', 'pt_2026_04_2')
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
  TEXT_HAS_PHRASE(input, output, 'unable to open') AS phrase_match,
  (
    TEXT_TOKEN_SCORE(input, output, 'unable') +
    TEXT_TOKEN_SCORE(input, output, 'open')
  ) AS text_score
FROM agent_observations
WHERE tenant = :tenant
  AND TEXT_HAS_TOKEN(input, output, 'unable')
  AND TEXT_HAS_TOKEN(input, output, 'open')
  AND TEXT_HAS_PHRASE(input, output, 'unable to open')
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
ORDER BY observations DESC, avg_latency_ms DESC
  , tool_name ASC, status ASC
LIMIT 50;

-- Q10
SELECT
  JSON_VALUE(payload, '$.provider.stop_reason') AS stop_reason,
  JSON_VALUE(payload, '$.provider.cache_hit') AS cache_hit,
  count(*) AS observations,
  avg(latency_ms) AS avg_latency_ms
FROM agent_observations
WHERE type = 'GENERATION'
GROUP BY JSON_VALUE(payload, '$.provider.stop_reason'), JSON_VALUE(payload, '$.provider.cache_hit')
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
  TEXT_HAS_PHRASE(input, output, 'unable to open') AS phrase_match,
  (
    TEXT_TOKEN_SCORE(input, output, 'unable') +
    TEXT_TOKEN_SCORE(input, output, 'open')
  ) AS text_score
FROM agent_observations
WHERE tenant = :tenant
  AND app = :app
  AND type IN ('GENERATION', 'TOOL', 'RETRIEVAL')
  AND TEXT_HAS_TOKEN(input, output, 'unable')
  AND TEXT_HAS_TOKEN(input, output, 'open')
  AND TEXT_HAS_PHRASE(input, output, 'unable to open')
ORDER BY phrase_match DESC, text_score DESC, latency_ms DESC, event_time DESC, trace_id DESC, observation_id DESC
LIMIT 50;

-- Q12
SELECT
  JSON_VALUE(payload, '$.attr.release_ring') AS release_ring,
  JSON_VALUE(payload, '$.attr.customer_tier') AS customer_tier,
  JSON_VALUE(payload, '$.attr.retrieval_strategy') AS retrieval_strategy,
  count(*) AS observations,
  avg(latency_ms) AS avg_latency_ms,
  sum(total_cost) AS total_cost
FROM agent_observations
WHERE type IN ('GENERATION', 'TOOL', 'RETRIEVAL')
GROUP BY
  JSON_VALUE(payload, '$.attr.release_ring'),
  JSON_VALUE(payload, '$.attr.customer_tier'),
  JSON_VALUE(payload, '$.attr.retrieval_strategy')
ORDER BY observations DESC, total_cost DESC
  , release_ring ASC, customer_tier ASC, retrieval_strategy ASC
LIMIT 50;

-- Q13
SELECT
  count(*) AS observations,
  count(DISTINCT trace_id) AS traces,
  max(event_time) AS last_event_time
FROM agent_observations
WHERE biz_date BETWEEN CAST(:start_date AS DATE) AND CAST(:end_date AS DATE)
  AND tenant = :tenant
  AND type IN ('GENERATION', 'TOOL', 'RETRIEVAL', 'EVENT')
  AND (
    TEXT_HAS_PHRASE(input, output, 'timeout awaiting headers')
    OR TEXT_HAS_PHRASE(input, output, 'retry budget depleted')
    OR TEXT_HAS_PHRASE(input, output, 'transient upstream failure')
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
WHERE tenant = :tenant
  AND app = :app
  AND type IN ('GENERATION', 'TOOL', 'EVENT')
  AND (
    LOWER(COALESCE(input, '')) LIKE '%deployment%'
    OR LOWER(COALESCE(output, '')) LIKE '%deployment%'
    OR LOWER(COALESCE(input, '')) LIKE '%rollback%'
    OR LOWER(COALESCE(output, '')) LIKE '%rollback%'
    OR LOWER(COALESCE(output, '')) LIKE '%transient%'
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
WHERE tenant = :tenant
  AND type IN ('GENERATION', 'TOOL', 'RETRIEVAL', 'EVENT')
  AND (
    TEXT_HAS_PHRASE(input, output, 'transient upstream failure')
    OR TEXT_HAS_PHRASE(input, output, 'retry budget depleted')
    OR TEXT_HAS_PHRASE(input, output, 'connector timeout')
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
  JSON_VALUE(payload, '$.attr.release_ring') AS release_ring,
  JSON_VALUE(payload, '$.attr.customer_tier') AS customer_tier,
  JSON_VALUE(payload, '$.attr.traffic_cluster') AS traffic_cluster
FROM agent_observations
WHERE tenant = :tenant
  AND environment = 'prod'
  AND type IN ('GENERATION', 'TOOL', 'RETRIEVAL')
  AND JSON_VALUE(payload, '$.attr.release_ring') = :release_ring
  AND JSON_VALUE(payload, '$.attr.customer_tier') = :customer_tier
  AND JSON_VALUE(payload, '$.attr.traffic_cluster') = :traffic_cluster
ORDER BY event_time DESC, trace_id DESC, observation_id DESC
LIMIT 50;

-- Q17
SELECT
  trace_id,
  observation_id,
  seq_no,
  type,
  status,
  JSON_VALUE(payload, '$.attr.request_key') AS request_key,
  JSON_VALUE(payload, '$.attr.workflow_variant') AS workflow_variant
FROM agent_observations
WHERE tenant = :tenant
  AND JSON_VALUE(payload, '$.attr.request_key') = :request_key
  AND JSON_VALUE(payload, '$.attr.workflow_variant') = :workflow_variant
ORDER BY seq_no ASC, observation_id ASC
LIMIT 100;

-- Q18
SELECT
  JSON_VALUE(payload, '$.attr.prompt_template_version') AS prompt_template_version,
  count(*) AS observations,
  count(DISTINCT trace_id) AS traces,
  avg(latency_ms) AS avg_latency_ms,
  sum(total_cost) AS total_cost
FROM agent_observations
WHERE type IN ('GENERATION', 'REASONING', 'TOOL')
GROUP BY JSON_VALUE(payload, '$.attr.prompt_template_version')
ORDER BY observations DESC, total_cost DESC, prompt_template_version ASC
LIMIT 20;

-- Q19
SELECT
  JSON_VALUE(payload, '$.attr.deployment_channel') AS deployment_channel,
  JSON_VALUE(payload, '$.attr.release_ring') AS release_ring,
  count(*) AS incident_observations,
  count(DISTINCT trace_id) AS incident_traces,
  avg(latency_ms) AS avg_latency_ms
FROM agent_observations
WHERE type IN ('GENERATION', 'TOOL', 'RETRIEVAL', 'EVENT')
  AND (
    TEXT_HAS_TOKEN(input, output, 'error')
    OR TEXT_HAS_TOKEN(input, output, 'timeout')
    OR TEXT_HAS_TOKEN(input, output, 'retry')
  )
GROUP BY JSON_VALUE(payload, '$.attr.deployment_channel'), JSON_VALUE(payload, '$.attr.release_ring')
ORDER BY incident_observations DESC, incident_traces DESC, deployment_channel ASC, release_ring ASC
LIMIT 20;

-- Q20
SELECT
  JSON_VALUE(payload, '$.attr.workflow_variant') AS workflow_variant,
  JSON_VALUE(payload, '$.attr.policy_pack') AS policy_pack,
  count(*) AS observations,
  count(DISTINCT tenant) AS tenants,
  avg(latency_ms) AS avg_latency_ms,
  sum(total_cost) AS total_cost
FROM agent_observations
WHERE type IN ('GENERATION', 'TOOL', 'RETRIEVAL', 'REASONING')
GROUP BY JSON_VALUE(payload, '$.attr.workflow_variant'), JSON_VALUE(payload, '$.attr.policy_pack')
ORDER BY observations DESC, total_cost DESC, workflow_variant ASC, policy_pack ASC
LIMIT 20;
