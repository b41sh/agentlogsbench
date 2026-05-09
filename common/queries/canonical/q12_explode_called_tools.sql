SELECT
    CAST(block['name'] AS STRING) AS called_tool_name,
    COUNT(*) AS count
FROM agent_call_logs_raw
LATERAL VIEW explode(v['response']['body']['content']) content_lv AS block
WHERE biz_date BETWEEN '2026-03-01' AND '2026-03-31'
  AND request_path = '/v1/messages'
  AND CAST(block['type'] AS STRING) = 'tool_use'
GROUP BY called_tool_name
ORDER BY count DESC, called_tool_name
LIMIT 1000;
