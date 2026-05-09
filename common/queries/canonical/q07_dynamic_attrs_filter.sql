SELECT
  event_time,
  trace_id,
  observation_id,
  type,
  status,
  payload
FROM agent_observations
WHERE (
    type = 'GENERATION'
    AND JSON_VALUE(payload, '$.provider.stop_reason') = 'tool_use'
  ) OR (
    type = 'TOOL'
    AND JSON_VALUE(payload, '$.tool_args.user_intent') = 'research'
    AND JSON_VALUE(payload, '$.tool_args.display_text') = 'reply'
  )
ORDER BY event_time DESC, trace_id DESC, observation_id DESC
LIMIT 50;
