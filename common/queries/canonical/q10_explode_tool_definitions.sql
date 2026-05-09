SELECT
    CAST(tool['name'] AS STRING) AS tool_name,
    COUNT(*) AS count
FROM agent_call_logs_raw
LATERAL VIEW explode(v['request']['body']['tools']) tool_lv AS tool
WHERE biz_date BETWEEN '2026-03-01' AND '2026-03-31'
  AND request_path = '/v1/messages'
GROUP BY tool_name
ORDER BY count DESC, tool_name
LIMIT 1000;
