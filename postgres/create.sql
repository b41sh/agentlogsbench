-- AIBENCH_PRELOAD_SCHEMA
DROP TABLE IF EXISTS __PG_TABLE__ CASCADE;

CREATE TABLE __PG_TABLE__ (
    event_time TIMESTAMP NOT NULL,
    biz_date DATE NOT NULL,
    trace_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    observation_id TEXT NOT NULL,
    parent_observation_id TEXT NULL,
    seq_no INTEGER NOT NULL,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    app TEXT NOT NULL,
    environment TEXT NOT NULL,
    task_category TEXT NOT NULL,
    trace_archetype TEXT NOT NULL,
    model TEXT NOT NULL,
    tool_name TEXT NULL,
    input TEXT NULL,
    output TEXT NULL,
    input_tokens BIGINT NOT NULL,
    output_tokens BIGINT NOT NULL,
    total_cost DOUBLE PRECISION NOT NULL,
    latency_ms INTEGER NOT NULL,
    tenant TEXT NOT NULL,
    payload JSONB NOT NULL
);

-- AIBENCH_POSTLOAD_SCHEMA
CREATE INDEX IF NOT EXISTS idx___PG_TABLE___observation_id ON __PG_TABLE__(observation_id);
CREATE INDEX IF NOT EXISTS idx___PG_TABLE___trace_seq ON __PG_TABLE__(biz_date, trace_id, seq_no);
CREATE INDEX IF NOT EXISTS idx___PG_TABLE___tenant_type_status_app ON __PG_TABLE__(tenant, type, status, app);
CREATE INDEX IF NOT EXISTS idx___PG_TABLE___payload_gin ON __PG_TABLE__ USING GIN (payload jsonb_path_ops);
CREATE INDEX IF NOT EXISTS idx___PG_TABLE___fts ON __PG_TABLE__
USING GIN (
  to_tsvector(
    'simple',
    lower(
      coalesce(input, '') || ' ' ||
      coalesce(output, '')
    )
  )
);
ANALYZE __PG_TABLE__;
