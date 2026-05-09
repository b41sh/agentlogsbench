SELECT
    biz_date,
    request_path,
    model,
    COUNT(*) AS calls
FROM agent_call_logs_raw
WHERE biz_date BETWEEN '2026-03-01' AND '2026-03-31'
  AND source = 'minimax'
GROUP BY biz_date, request_path, model
ORDER BY biz_date, calls DESC, request_path, model;
