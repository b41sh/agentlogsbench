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
LIMIT 50;
