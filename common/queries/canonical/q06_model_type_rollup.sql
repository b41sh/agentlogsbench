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
LIMIT 50;
