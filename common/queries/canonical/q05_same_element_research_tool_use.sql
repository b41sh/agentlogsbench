SELECT
    request_id,
    session_id,
    model,
    CAST(v['duration_ms'] AS BIGINT) AS duration_ms
FROM agent_call_logs_raw
WHERE biz_date BETWEEN '2026-03-01' AND '2026-03-31'
  AND request_path = '/v1/messages'
  AND stop_reason = 'tool_use'
  AND search('NESTED(v.request.body.messages.content, type:tool_use AND (input.user_intent:explore OR input.user_intent:research OR input.user_intent:investigate OR input.user_intent:探索 OR input.user_intent:调研) AND (input.display_text:research OR input.display_text:explore OR input.display_text:discover OR input.display_text:community OR input.display_text:调研 OR input.display_text:检索 OR input.display_text:探索 OR input.display_text:社区))')
ORDER BY biz_date, request_id
LIMIT 200;
