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
