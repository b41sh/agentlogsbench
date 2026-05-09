SELECT
  child.trace_id,
  child.seq_no,
  child.observation_id,
  child.parent_observation_id,
  parent.type AS parent_type,
  child.type AS child_type,
  child.status,
  child.tool_name
FROM agent_observations AS child
LEFT JOIN agent_observations AS parent
  ON child.parent_observation_id = parent.observation_id
WHERE child.trace_id = :trace_id
ORDER BY child.seq_no ASC;
