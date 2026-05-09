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
WHERE biz_date BETWEEN CAST(@start_date_param AS DATE) AND CAST(@end_date_param AS DATE)
  AND tenant = @tenant_param
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
WHERE biz_date BETWEEN CAST(@start_date_param AS DATE) AND CAST(@end_date_param AS DATE)
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
WHERE trace_id = @trace_id_param
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
WHERE child.trace_id = @trace_id_param
ORDER BY child.seq_no ASC;

-- Q05
SELECT
  event_time,
  trace_id,
  observation_id,
  tool_name,
  latency_ms,
  2 /* guaranteed by MATCH_ALL 'unable open': 'unable' + 'open' */ AS text_score,
  payload
FROM agent_observations
WHERE type = 'TOOL'
  AND status = 'error'
  AND tenant = @tenant_param
  AND app = @app_param
  AND (
    input MATCH_ALL 'unable open'
    OR output MATCH_ALL 'unable open'
  )
ORDER BY latency_ms DESC, event_time DESC
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
  AND CAST(payload['attr']['release_ring'] AS STRING) IN ('stable', 'canary')
  AND CAST(payload['attr']['retrieval_strategy'] AS STRING) IN ('hybrid', 'hybrid_rerank')
  AND CAST(payload['attr']['surface'] AS STRING) IN ('api', 'workflow_runner')
  AND CAST(payload['attr']['prompt_template_version'] AS STRING) IN ('pt_2026_03_2', 'pt_2026_04_1', 'pt_2026_04_2')
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
  TRUE /* guaranteed by MATCH_PHRASE 'unable to open' */ AS phrase_match,
  2 /* guaranteed by MATCH_ALL 'unable open': 'unable' + 'open' */ AS text_score
FROM agent_observations
WHERE tenant = @tenant_param
  AND (
    input MATCH_ALL 'unable open'
    OR output MATCH_ALL 'unable open'
  )
  AND (
    input MATCH_PHRASE 'unable to open'
    OR output MATCH_PHRASE 'unable to open'
  )
ORDER BY event_time DESC, trace_id DESC, observation_id DESC
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
  CAST(payload['provider']['stop_reason'] AS STRING) AS stop_reason,
  CASE WHEN CAST(payload['provider']['cache_hit'] AS INT) <> 0 THEN 'true' ELSE 'false' END AS cache_hit,
  count(*) AS observations,
  avg(latency_ms) AS avg_latency_ms
FROM agent_observations
WHERE type = 'GENERATION'
GROUP BY CAST(payload['provider']['stop_reason'] AS STRING), CASE WHEN CAST(payload['provider']['cache_hit'] AS INT) <> 0 THEN 'true' ELSE 'false' END
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
  TRUE /* guaranteed by MATCH_PHRASE 'unable to open' */ AS phrase_match,
  2 /* guaranteed by MATCH_ALL 'unable open': 'unable' + 'open' */ AS text_score
FROM agent_observations
WHERE tenant = @tenant_param
  AND app = @app_param
  AND type IN ('GENERATION', 'TOOL', 'RETRIEVAL')
  AND (
    input MATCH_ALL 'unable open'
    OR output MATCH_ALL 'unable open'
  )
  AND (
    input MATCH_PHRASE 'unable to open'
    OR output MATCH_PHRASE 'unable to open'
  )
ORDER BY latency_ms DESC, event_time DESC, trace_id DESC, observation_id DESC
LIMIT 50;

-- Q12
SELECT
  CAST(payload['attr']['release_ring'] AS STRING) AS release_ring,
  CAST(payload['attr']['customer_tier'] AS STRING) AS customer_tier,
  CAST(payload['attr']['retrieval_strategy'] AS STRING) AS retrieval_strategy,
  count(*) AS observations,
  avg(latency_ms) AS avg_latency_ms,
  sum(total_cost) AS total_cost
FROM agent_observations
WHERE type IN ('GENERATION', 'TOOL', 'RETRIEVAL')
GROUP BY
  CAST(payload['attr']['release_ring'] AS STRING),
  CAST(payload['attr']['customer_tier'] AS STRING),
  CAST(payload['attr']['retrieval_strategy'] AS STRING)
ORDER BY observations DESC, total_cost DESC
  , release_ring ASC, customer_tier ASC, retrieval_strategy ASC
LIMIT 50;

-- Q13
SELECT
  count(*) AS observations,
  count(DISTINCT trace_id) AS traces,
  max(event_time) AS last_event_time
FROM agent_observations
WHERE biz_date BETWEEN CAST(@start_date_param AS DATE) AND CAST(@end_date_param AS DATE)
  AND tenant = @tenant_param
  AND type IN ('GENERATION', 'TOOL', 'RETRIEVAL', 'EVENT')
  AND (
    input MATCH_PHRASE 'timeout awaiting headers'
    OR output MATCH_PHRASE 'timeout awaiting headers'
    OR input MATCH_PHRASE 'retry budget depleted'
    OR output MATCH_PHRASE 'retry budget depleted'
    OR input MATCH_PHRASE 'transient upstream failure'
    OR output MATCH_PHRASE 'transient upstream failure'
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
WHERE tenant = @tenant_param
  AND app = @app_param
  AND type IN ('GENERATION', 'TOOL', 'EVENT')
  AND (
    lower(ifnull(input, '')) LIKE '%deployment%'
    OR lower(ifnull(output, '')) LIKE '%deployment%'
    OR lower(ifnull(input, '')) LIKE '%rollback%'
    OR lower(ifnull(output, '')) LIKE '%rollback%'
    OR lower(ifnull(output, '')) LIKE '%transient%'
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
WHERE tenant = @tenant_param
  AND type IN ('GENERATION', 'TOOL', 'RETRIEVAL', 'EVENT')
  AND (
    input MATCH_PHRASE 'transient upstream failure'
    OR output MATCH_PHRASE 'transient upstream failure'
    OR input MATCH_PHRASE 'retry budget depleted'
    OR output MATCH_PHRASE 'retry budget depleted'
    OR input MATCH_PHRASE 'connector timeout'
    OR output MATCH_PHRASE 'connector timeout'
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
  CAST(payload['attr']['release_ring'] AS STRING) AS release_ring,
  CAST(payload['attr']['customer_tier'] AS STRING) AS customer_tier,
  CAST(payload['attr']['traffic_cluster'] AS STRING) AS traffic_cluster
FROM agent_observations
WHERE tenant = @tenant_param
  AND environment = 'prod'
  AND type IN ('GENERATION', 'TOOL', 'RETRIEVAL')
  AND CAST(payload['attr']['release_ring'] AS STRING) = @release_ring_param
  AND CAST(payload['attr']['customer_tier'] AS STRING) = @customer_tier_param
  AND CAST(payload['attr']['traffic_cluster'] AS STRING) = @traffic_cluster_param
ORDER BY event_time DESC, trace_id DESC, observation_id DESC
LIMIT 50;

-- Q17
SELECT
  trace_id,
  observation_id,
  seq_no,
  type,
  status,
  CAST(payload['attr']['request_key'] AS STRING) AS request_key,
  CAST(payload['attr']['workflow_variant'] AS STRING) AS workflow_variant
FROM agent_observations
WHERE tenant = @tenant_param
  AND CAST(payload['attr']['request_key'] AS STRING) = @request_key_param
  AND CAST(payload['attr']['workflow_variant'] AS STRING) = @workflow_variant_param
ORDER BY seq_no ASC, observation_id ASC
LIMIT 100;

-- Q18
SELECT
  CAST(payload['attr']['prompt_template_version'] AS STRING) AS prompt_template_version,
  count(*) AS observations,
  count(DISTINCT trace_id) AS traces,
  avg(latency_ms) AS avg_latency_ms,
  sum(total_cost) AS total_cost
FROM agent_observations
WHERE type IN ('GENERATION', 'REASONING', 'TOOL')
GROUP BY CAST(payload['attr']['prompt_template_version'] AS STRING)
ORDER BY observations DESC, total_cost DESC, prompt_template_version ASC
LIMIT 20;

-- Q19
SELECT
  CAST(payload['attr']['deployment_channel'] AS STRING) AS deployment_channel,
  CAST(payload['attr']['release_ring'] AS STRING) AS release_ring,
  count(*) AS incident_observations,
  count(DISTINCT trace_id) AS incident_traces,
  avg(latency_ms) AS avg_latency_ms
FROM agent_observations
WHERE type IN ('GENERATION', 'TOOL', 'RETRIEVAL', 'EVENT')
  AND (
    input MATCH_ANY 'error timeout retry'
    OR output MATCH_ANY 'error timeout retry'
  )
GROUP BY CAST(payload['attr']['deployment_channel'] AS STRING), CAST(payload['attr']['release_ring'] AS STRING)
ORDER BY incident_observations DESC, incident_traces DESC, deployment_channel ASC, release_ring ASC
LIMIT 20;

-- Q20
SELECT
  CAST(payload['attr']['workflow_variant'] AS STRING) AS workflow_variant,
  CAST(payload['attr']['policy_pack'] AS STRING) AS policy_pack,
  count(*) AS observations,
  count(DISTINCT tenant) AS tenants,
  avg(latency_ms) AS avg_latency_ms,
  sum(total_cost) AS total_cost
FROM agent_observations
WHERE type IN ('GENERATION', 'TOOL', 'RETRIEVAL', 'REASONING')
GROUP BY CAST(payload['attr']['workflow_variant'] AS STRING), CAST(payload['attr']['policy_pack'] AS STRING)
ORDER BY observations DESC, total_cost DESC, workflow_variant ASC, policy_pack ASC
LIMIT 20;
