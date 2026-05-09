SELECT
    CAST(item['type'] AS STRING) AS block_type,
    COUNT(*) AS count
FROM agent_call_logs_raw
LATERAL VIEW explode(v['request']['body']['messages']) msg_lv AS message
LATERAL VIEW explode(message['content']) item_lv AS item
WHERE biz_date BETWEEN '2026-03-01' AND '2026-03-31'
  AND request_path = '/v1/messages'
GROUP BY block_type
ORDER BY count DESC, block_type
LIMIT 100;
