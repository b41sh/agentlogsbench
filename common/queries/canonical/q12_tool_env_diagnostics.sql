SELECT
  JSON_VALUE(payload, '$.tool_args.cwd') AS cwd,
  JSON_VALUE(payload, '$.tool_args.env.APP_NAME') AS app_name,
  count(*) AS observations
FROM agent_observations
WHERE type = 'TOOL'
GROUP BY JSON_VALUE(payload, '$.tool_args.cwd'), JSON_VALUE(payload, '$.tool_args.env.APP_NAME')
ORDER BY observations DESC
LIMIT 50;
