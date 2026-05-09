DROP TABLE IF EXISTS __DUCKDB_TABLE__;

CREATE TABLE __DUCKDB_TABLE__ (
    event_time TIMESTAMP NOT NULL,
    biz_date DATE NOT NULL,
    trace_id VARCHAR NOT NULL,
    session_id VARCHAR NOT NULL,
    observation_id VARCHAR NOT NULL,
    parent_observation_id VARCHAR,
    seq_no INTEGER NOT NULL,
    type VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    app VARCHAR NOT NULL,
    environment VARCHAR NOT NULL,
    task_category VARCHAR NOT NULL,
    trace_archetype VARCHAR NOT NULL,
    model VARCHAR NOT NULL,
    tool_name VARCHAR,
    input VARCHAR,
    output VARCHAR,
    input_tokens BIGINT NOT NULL,
    output_tokens BIGINT NOT NULL,
    total_cost DOUBLE NOT NULL,
    latency_ms INTEGER NOT NULL,
    tenant VARCHAR NOT NULL,
    payload VARIANT NOT NULL
);
