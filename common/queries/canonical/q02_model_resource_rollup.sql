SELECT
    model,
    COUNT(*) AS calls,
    SUM(IFNULL(CAST(v['response']['body']['usage']['input_tokens'] AS BIGINT), 0)) AS input_tokens,
    SUM(IFNULL(CAST(v['response']['body']['usage']['output_tokens'] AS BIGINT), 0)) AS output_tokens,
    SUM(IFNULL(CAST(v['response']['body']['usage']['cache_read_input_tokens'] AS BIGINT), 0)) AS cache_read_tokens,
    AVG(CAST(v['duration_ms'] AS BIGINT)) AS avg_duration_ms,
    percentile_approx(CAST(v['duration_ms'] AS BIGINT), 0.95) AS p95_duration_ms
FROM agent_call_logs_raw
WHERE biz_date BETWEEN '2026-03-01' AND '2026-03-31'
  AND request_path = '/v1/messages'
GROUP BY model
ORDER BY input_tokens DESC, p95_duration_ms DESC, model;
