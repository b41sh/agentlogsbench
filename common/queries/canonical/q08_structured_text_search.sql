SELECT
  event_time,
  trace_id,
  observation_id,
  type,
  status,
  input,
  output,
  TEXT_HAS_PHRASE(input, output, 'unable to open') AS phrase_match,
  (
    TEXT_TOKEN_SCORE(input, output, 'unable') +
    TEXT_TOKEN_SCORE(input, output, 'open')
  ) AS text_score
FROM agent_observations
WHERE tenant = :tenant
  AND TEXT_HAS_TOKEN(input, output, 'unable')
  AND TEXT_HAS_TOKEN(input, output, 'open')
  AND TEXT_HAS_PHRASE(input, output, 'unable to open')
ORDER BY phrase_match DESC, text_score DESC, event_time DESC, trace_id DESC, observation_id DESC
LIMIT 50;
