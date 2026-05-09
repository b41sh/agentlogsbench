SELECT
  trace_id,
  observation_count,
  total_cost,
  total_latency_ms
FROM (
  SELECT
    trace_id,
    count(*) AS observation_count,
    sum(total_cost) AS total_cost,
    sum(latency_ms) AS total_latency_ms
  FROM agent_observations
  GROUP BY trace_id
) AS trace_rollups
WHERE total_cost > 0
ORDER BY total_cost DESC, total_latency_ms DESC
LIMIT 50;
