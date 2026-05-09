SELECT
    request_id,
    session_id,
    model,
    http_status,
    stop_reason,
    CAST(v['duration_ms'] AS BIGINT) AS duration_ms
FROM agent_call_logs_raw
WHERE biz_date BETWEEN '2026-03-01' AND '2026-03-31'
  AND source = 'minimax'
  AND tenant = 'demo'
  AND request_path = '/v1/messages'
  AND search('permission denied OR access denied OR unauthorized OR forbidden OR timeout OR timed out OR rate limit')
ORDER BY biz_date DESC, duration_ms DESC, request_id
LIMIT 200;
