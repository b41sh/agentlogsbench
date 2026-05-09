SELECT
    request_id,
    session_id,
    model,
    CAST(v['duration_ms'] AS BIGINT) AS duration_ms
FROM agent_call_logs_raw
WHERE biz_date BETWEEN '2026-03-01' AND '2026-03-31'
  AND request_path = '/v1/messages'
  AND stop_reason = 'tool_use'
  AND search('NESTED(v.request.body.messages.content, type:tool_use AND (input.user_intent:reply OR input.user_intent:engage OR input.user_intent:互动 OR input.user_intent:讨论) AND (input.display_text:reply OR input.display_text:post OR input.display_text:comment OR input.display_text:回复 OR input.display_text:帖子 OR input.display_text:评论))')
ORDER BY biz_date, request_id
LIMIT 200;
