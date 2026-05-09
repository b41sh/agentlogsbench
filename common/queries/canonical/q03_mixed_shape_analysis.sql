SELECT
    request_path,
    model,
    COUNT(*) AS calls,
    SUM(
        CASE
            WHEN request_path = '/v1/messages'
                THEN IFNULL(CAST(v['response']['body']['usage']['input_tokens'] AS BIGINT), 0)
            WHEN request_path = '/v1/messages/count_tokens'
                THEN IFNULL(CAST(v['response']['body']['input_tokens'] AS BIGINT), 0)
            ELSE 0
        END
    ) AS effective_input_tokens,
    AVG(CAST(v['duration_ms'] AS BIGINT)) AS avg_duration_ms
FROM agent_call_logs_raw
WHERE biz_date BETWEEN '2026-03-01' AND '2026-03-31'
  AND request_path IN ('/v1/messages', '/v1/messages/count_tokens')
GROUP BY request_path, model
ORDER BY effective_input_tokens DESC, calls DESC, request_path, model;
