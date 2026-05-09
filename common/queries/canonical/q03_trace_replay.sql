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
WHERE trace_id = :trace_id
ORDER BY seq_no ASC;
