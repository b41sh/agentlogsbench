CREATE DATABASE IF NOT EXISTS __CH_DB__;
DROP TABLE IF EXISTS __CH_DB__.__CH_TABLE__;

CREATE TABLE __CH_DB__.__CH_TABLE__ (
    event_time DateTime,
    biz_date Date,
    trace_id String,
    session_id String,
    observation_id String,
    parent_observation_id Nullable(String),
    seq_no UInt32,
    type LowCardinality(String),
    status LowCardinality(String),
    tenant String,
    app String,
    environment LowCardinality(String),
    task_category String,
    trace_archetype String,
    model String,
    tool_name Nullable(String),
    input Nullable(String),
    output Nullable(String),
    input_tokens UInt64,
    output_tokens UInt64,
    total_cost Float64,
    latency_ms UInt32,
    payload JSON,
    INDEX idx_text_search (
        lowerUTF8(
            concat(
                ifNull(input, ''),
                ' ',
                ifNull(output, '')
            )
        )
    ) TYPE text(tokenizer = 'splitByNonAlpha') GRANULARITY 1
)
ENGINE = MergeTree
ORDER BY (biz_date, trace_id, seq_no)
SETTINGS
    object_serialization_version = 'v3',
    dynamic_serialization_version = 'v3',
    object_shared_data_serialization_version = 'advanced';
