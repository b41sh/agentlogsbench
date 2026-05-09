CREATE DATABASE IF NOT EXISTS __DORIS_DB__;
USE __DORIS_DB__;

DROP TABLE IF EXISTS __DORIS_TABLE__;

CREATE TABLE __DORIS_TABLE__ (
    trace_id VARCHAR(128),
    observation_id VARCHAR(128),
    seq_no INT,
    event_time DATETIME,
    biz_date DATE,
    session_id STRING,
    parent_observation_id STRING,
    type STRING,
    status STRING,
    tenant STRING,
    app STRING,
    environment STRING,
    task_category STRING,
    trace_archetype STRING,
    model STRING,
    tool_name STRING,
    input STRING,
    output STRING,
    input_tokens BIGINT,
    output_tokens BIGINT,
    total_cost DOUBLE,
    latency_ms BIGINT,
    payload VARIANT,
    INDEX idx_input_text(input) USING INVERTED PROPERTIES(
        "parser" = "unicode",
        "support_phrase" = "true",
        "char_filter_type" = "char_replace",
        "char_filter_pattern" = "._",
        "char_filter_replacement" = " "
    ),
    INDEX idx_output_text(output) USING INVERTED PROPERTIES(
        "parser" = "unicode",
        "support_phrase" = "true",
        "char_filter_type" = "char_replace",
        "char_filter_pattern" = "._",
        "char_filter_replacement" = " "
    )
)
ENGINE=OLAP
DUPLICATE KEY(trace_id, observation_id, seq_no)
PROPERTIES(
    "replication_num" = "1",
    "compression" = "zstd",
    "inverted_index_storage_format" = "V3",
    "bloom_filter_columns" = "payload"
);
