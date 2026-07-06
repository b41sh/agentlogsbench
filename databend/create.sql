CREATE DATABASE IF NOT EXISTS __DATABEND_DB__;
USE __DATABEND_DB__;

DROP TABLE IF EXISTS __DATABEND_TABLE__;

CREATE TABLE __DATABEND_TABLE__ (
    event_time TIMESTAMP NOT NULL,
    biz_date DATE NOT NULL,
    trace_id STRING NOT NULL,
    session_id STRING NOT NULL,
    observation_id STRING NOT NULL,
    parent_observation_id STRING NULL,
    seq_no INT NOT NULL,
    type STRING NOT NULL,
    status STRING NOT NULL,
    tenant STRING NOT NULL,
    app STRING NOT NULL,
    environment STRING NOT NULL,
    task_category STRING NOT NULL,
    trace_archetype STRING NOT NULL,
    model STRING NOT NULL,
    tool_name STRING NULL,
    input STRING NULL,
    output STRING NULL,
    input_tokens BIGINT NOT NULL,
    output_tokens BIGINT NOT NULL,
    total_cost DOUBLE NOT NULL,
    latency_ms BIGINT NOT NULL,
    payload VARIANT NOT NULL,
    INVERTED INDEX idx_agent_observations_text (input, output)
)
CLUSTER BY (biz_date, trace_id, seq_no)
enable_virtual_column=true;
