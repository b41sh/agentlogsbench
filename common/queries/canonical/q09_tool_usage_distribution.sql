SELECT
  tool_name,
  status,
  count(*) AS observations,
  avg(latency_ms) AS avg_latency_ms
FROM agent_observations
WHERE type = 'TOOL'
GROUP BY tool_name, status
ORDER BY observations DESC, avg_latency_ms DESC
LIMIT 50;
