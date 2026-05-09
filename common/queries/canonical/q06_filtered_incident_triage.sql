SELECT
    request_id,
    session_id,
    model,
    http_status,
    stop_reason,
    CAST(v['duration_ms'] AS BIGINT) AS duration_ms,
    IFNULL(CAST(v['response']['body']['usage']['input_tokens'] AS BIGINT), 0) AS input_tokens,
    IFNULL(CAST(v['response']['body']['usage']['output_tokens'] AS BIGINT), 0) AS output_tokens
FROM agent_call_logs_raw
WHERE event_time >= '2026-03-20 00:00:00'
  AND event_time < '2026-03-21 00:00:00'
  AND tenant = 'demo'
  AND request_path = '/v1/messages'
  AND (http_status >= 400 OR CAST(v['duration_ms'] AS BIGINT) >= 10000)
ORDER BY duration_ms DESC, request_id
LIMIT 100;
