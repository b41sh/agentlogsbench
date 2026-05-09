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
