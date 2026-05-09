SELECT
  JSON_VALUE(payload, '$.provider.stop_reason') AS stop_reason,
  JSON_VALUE(payload, '$.provider.cache_hit') AS cache_hit,
  count(*) AS observations,
  avg(latency_ms) AS avg_latency_ms
FROM agent_observations
WHERE type = 'GENERATION'
GROUP BY JSON_VALUE(payload, '$.provider.stop_reason'), JSON_VALUE(payload, '$.provider.cache_hit')
ORDER BY observations DESC, avg_latency_ms DESC
LIMIT 50;
