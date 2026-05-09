SELECT
    request_id,
    session_id,
    model,
    CAST(v['response']['body']['input_tokens'] AS BIGINT) AS estimated_input_tokens,
    CAST(v['request']['body']['messages'] AS STRING) AS messages_json
FROM agent_call_logs_raw
WHERE biz_date BETWEEN '2026-03-01' AND '2026-03-31'
  AND request_path = '/v1/messages/count_tokens'
ORDER BY estimated_input_tokens DESC, request_id
LIMIT 100;
