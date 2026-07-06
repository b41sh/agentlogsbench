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
WHERE biz_date BETWEEN CAST(:start_date_param AS DATE) AND CAST(:end_date_param AS DATE)
  AND tenant = :tenant_param
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
WHERE biz_date BETWEEN CAST(:start_date_param AS DATE) AND CAST(:end_date_param AS DATE)
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
WHERE trace_id = :trace_id_param
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
WHERE child.trace_id = :trace_id_param
ORDER BY child.seq_no ASC;

-- Q05
SELECT
  event_time,
  trace_id,
  observation_id,
  tool_name,
  latency_ms,
  SCORE() AS text_score,
  payload
FROM agent_observations
WHERE type = 'TOOL'
  AND status = 'error'
  AND tenant = :tenant_param
  AND app = :app_param
  /* contract markers: 'unable' 'open' */
  AND MATCH('input, output', 'unable open', 'operator=AND')
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
  AND payload #>> '{attr,release_ring}' IN ('stable', 'canary')
  AND payload #>> '{attr,retrieval_strategy}' IN ('hybrid', 'hybrid_rerank')
  AND payload #>> '{attr,surface}' IN ('api', 'workflow_runner')
  AND payload #>> '{attr,prompt_template_version}' IN ('pt_2026_03_2', 'pt_2026_04_1', 'pt_2026_04_2')
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
  TRUE AS phrase_match,
  SCORE() AS text_score
FROM agent_observations
WHERE tenant = :tenant_param
  /* contract markers: 'unable' 'open' 'unable to open' */
  AND MATCH('input, output', '"unable to open"', 'operator=AND')
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
  payload #>> '{provider,stop_reason}' AS stop_reason,
  payload #>> '{provider,cache_hit}' AS cache_hit,
  count(*) AS observations,
  avg(latency_ms) AS avg_latency_ms
FROM agent_observations
WHERE type = 'GENERATION'
GROUP BY payload #>> '{provider,stop_reason}', payload #>> '{provider,cache_hit}'
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
  TRUE AS phrase_match,
  SCORE() AS text_score
FROM agent_observations
WHERE tenant = :tenant_param
  AND app = :app_param
  AND type IN ('GENERATION', 'TOOL', 'RETRIEVAL')
  /* contract markers: 'unable' 'open' 'unable to open' */
  AND MATCH('input, output', '"unable to open"', 'operator=AND')
ORDER BY phrase_match DESC, text_score DESC, latency_ms DESC, event_time DESC, trace_id DESC, observation_id DESC
LIMIT 50;

-- Q12
SELECT
  payload #>> '{attr,release_ring}' AS release_ring,
  payload #>> '{attr,customer_tier}' AS customer_tier,
  payload #>> '{attr,retrieval_strategy}' AS retrieval_strategy,
  count(*) AS observations,
  avg(latency_ms) AS avg_latency_ms,
  sum(total_cost) AS total_cost
FROM agent_observations
WHERE type IN ('GENERATION', 'TOOL', 'RETRIEVAL')
GROUP BY
  payload #>> '{attr,release_ring}',
  payload #>> '{attr,customer_tier}',
  payload #>> '{attr,retrieval_strategy}'
ORDER BY observations DESC, total_cost DESC, release_ring ASC, customer_tier ASC, retrieval_strategy ASC
LIMIT 50;

-- Q13
SELECT
  count(*) AS observations,
  count(DISTINCT trace_id) AS traces,
  max(event_time) AS last_event_time
FROM agent_observations
WHERE biz_date BETWEEN CAST(:start_date_param AS DATE) AND CAST(:end_date_param AS DATE)
  AND tenant = :tenant_param
  AND type IN ('GENERATION', 'TOOL', 'RETRIEVAL', 'EVENT')
  AND MATCH('input, output', '"timeout awaiting headers" OR "retry budget depleted" OR "transient upstream failure"', 'operator=OR');

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
WHERE tenant = :tenant_param
  AND app = :app_param
  AND type IN ('GENERATION', 'TOOL', 'EVENT')
  AND MATCH('input, output', 'deployment rollback transient', 'operator=OR')
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
WHERE tenant = :tenant_param
  AND type IN ('GENERATION', 'TOOL', 'RETRIEVAL', 'EVENT')
  AND MATCH('input, output', '"transient upstream failure" OR "retry budget depleted" OR "connector timeout"', 'operator=OR')
ORDER BY latency_ms DESC, event_time DESC, trace_id DESC, observation_id DESC
LIMIT 50;

-- Q16
SELECT
  event_time,
  trace_id,
  observation_id,
  type,
  status,
  payload #>> '{attr,release_ring}' AS release_ring,
  payload #>> '{attr,customer_tier}' AS customer_tier,
  payload #>> '{attr,traffic_cluster}' AS traffic_cluster
FROM agent_observations
WHERE tenant = :tenant_param
  AND environment = 'prod'
  AND type IN ('GENERATION', 'TOOL', 'RETRIEVAL')
  AND payload #>> '{attr,release_ring}' = :release_ring_param
  AND payload #>> '{attr,customer_tier}' = :customer_tier_param
  AND payload #>> '{attr,traffic_cluster}' = :traffic_cluster_param
ORDER BY event_time DESC, trace_id DESC, observation_id DESC
LIMIT 50;

-- Q17
SELECT
  trace_id,
  observation_id,
  seq_no,
  type,
  status,
  payload #>> '{attr,request_key}' AS request_key,
  payload #>> '{attr,workflow_variant}' AS workflow_variant
FROM agent_observations
WHERE tenant = :tenant_param
  AND payload #>> '{attr,request_key}' = :request_key_param
  AND payload #>> '{attr,workflow_variant}' = :workflow_variant_param
ORDER BY seq_no ASC, observation_id ASC
LIMIT 100;

-- Q18
SELECT
  payload #>> '{attr,prompt_template_version}' AS prompt_template_version,
  count(*) AS observations,
  count(DISTINCT trace_id) AS traces,
  avg(latency_ms) AS avg_latency_ms,
  sum(total_cost) AS total_cost
FROM agent_observations
WHERE type IN ('GENERATION', 'REASONING', 'TOOL')
GROUP BY payload #>> '{attr,prompt_template_version}'
ORDER BY observations DESC, total_cost DESC, prompt_template_version ASC
LIMIT 20;

-- Q19
SELECT
  payload #>> '{attr,deployment_channel}' AS deployment_channel,
  payload #>> '{attr,release_ring}' AS release_ring,
  count(*) AS incident_observations,
  count(DISTINCT trace_id) AS incident_traces,
  avg(latency_ms) AS avg_latency_ms
FROM agent_observations
WHERE type IN ('GENERATION', 'TOOL', 'RETRIEVAL', 'EVENT')
  AND MATCH('input, output', 'error timeout retry', 'operator=OR')
GROUP BY payload #>> '{attr,deployment_channel}', payload #>> '{attr,release_ring}'
ORDER BY incident_observations DESC, incident_traces DESC, deployment_channel ASC, release_ring ASC
LIMIT 20;

-- Q20
SELECT
  payload #>> '{attr,workflow_variant}' AS workflow_variant,
  payload #>> '{attr,policy_pack}' AS policy_pack,
  count(*) AS observations,
  count(DISTINCT tenant) AS tenants,
  avg(latency_ms) AS avg_latency_ms,
  sum(total_cost) AS total_cost
FROM agent_observations
WHERE type IN ('GENERATION', 'TOOL', 'RETRIEVAL', 'REASONING')
GROUP BY payload #>> '{attr,workflow_variant}', payload #>> '{attr,policy_pack}'
ORDER BY observations DESC, total_cost DESC, workflow_variant ASC, policy_pack ASC
LIMIT 20;
