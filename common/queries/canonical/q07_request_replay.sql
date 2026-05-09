SELECT
    request_id,
    session_id,
    request_path,
    model,
    http_status,
    stop_reason,
    CAST(v['duration_ms'] AS BIGINT) AS duration_ms,
    CAST(v['request'] AS STRING) AS request_json,
    CAST(v['filtered_request'] AS STRING) AS filtered_request_json,
    CAST(v['response'] AS STRING) AS response_json
FROM agent_call_logs_raw
WHERE request_id = '<request_id_from_incident>';
