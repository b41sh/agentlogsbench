#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${SCRIPT_DIR}/runtime_env.sh"
source "${ROOT_DIR}/agentlogsbench/common/benchmark_lib.sh"

PG_CLIENT_DIR="${PG_CLIENT_DIR:-$(resolve_pg_client_dir || true)}"
PG_HOST="${PG_HOST:-127.0.0.1}"
PG_PORT="${PG_PORT:-55432}"
PG_USER="${PG_USER:-postgres}"
PG_DB="${PG_DB:-agentlogsbench_pg}"
PG_TABLE="${PG_TABLE:-agent_observations}"
DATA_GLOB="${DATA_GLOB:-${ROOT_DIR}/agentlogsbench/common/generated/small/agent_observations_s.ndjson}"
CREATE_SQL="${CREATE_SQL:-${SCRIPT_DIR}/create.sql}"

shopt -s nullglob
files=( ${DATA_GLOB} )
shopt -u nullglob

if [ "${#files[@]}" -eq 0 ]; then
    echo "No files matched DATA_GLOB=${DATA_GLOB}" >&2
    exit 1
fi

benchmark_log "postgres" "Preparing schema ${PG_DB}.${PG_TABLE}"
run_python_with_pgclient - "${PG_HOST}" "${PG_PORT}" "${PG_USER}" "${PG_DB}" "${PG_TABLE}" "${CREATE_SQL}" "${files[@]}" <<'PY'
from __future__ import annotations

from datetime import datetime
import gzip
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Iterator

import psycopg2

PRELOAD_MARKER = "-- AIBENCH_PRELOAD_SCHEMA"
POSTLOAD_MARKER = "-- AIBENCH_POSTLOAD_SCHEMA"


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [postgres] {message}", file=sys.stderr, flush=True)


def split_schema_sections(schema_sql: str) -> tuple[str, str]:
    preload: list[str] = []
    postload: list[str] = []
    current: list[str] | None = None
    for raw_line in schema_sql.splitlines():
        stripped = raw_line.strip()
        if stripped == PRELOAD_MARKER:
            current = preload
            continue
        if stripped == POSTLOAD_MARKER:
            current = postload
            continue
        if current is not None:
            current.append(raw_line)
    if not preload or not postload:
        raise SystemExit(
            f"{create_sql} must define both {PRELOAD_MARKER} and {POSTLOAD_MARKER}"
        )
    return "\n".join(preload), "\n".join(postload)


def execute_statements(cursor, sql_text: str) -> None:
    for statement in sql_text.split(";"):
        statement = statement.strip()
        if statement:
            cursor.execute(statement)


def collect_statements(sql_text: str) -> list[str]:
    statements: list[str] = []
    for statement in sql_text.split(";"):
        statement = statement.strip()
        if statement:
            statements.append(statement)
    return statements


def copy_escape(value) -> str:
    if value is None:
        return r"\N"
    text = str(value)
    return (
        text.replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def iter_lines(file_path: str, pigz_bin: str | None, decompress_threads: str) -> Iterator[str]:
    if file_path.endswith(".gz") and pigz_bin:
        proc = subprocess.Popen(
            [pigz_bin, "-dc", "-p", decompress_threads, file_path],
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        if proc.stdout is None:
            raise SystemExit(f"Unable to stream {file_path} with pigz")
        try:
            for line in proc.stdout:
                yield line
        finally:
            proc.stdout.close()
            if proc.wait() != 0:
                raise SystemExit(f"pigz failed while reading {file_path}")
        return

    if file_path.endswith(".gz"):
        opener = gzip.open
    else:
        opener = open
    with opener(file_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            yield line


host, port, user, db, table, create_sql, *files = sys.argv[1:]
if not files:
    raise SystemExit("No files were provided to postgres/import.sh")

copy_batch_rows = int(os.environ.get("PG_COPY_BATCH_ROWS", "5000"))
copy_commit_rows = int(os.environ.get("PG_COPY_COMMIT_ROWS", "100000"))
decompress_threads = os.environ.get("PG_DECOMPRESS_THREADS", str(min(8, os.cpu_count() or 1)))
pigz_bin = shutil.which("pigz")
maintenance_work_mem = os.environ.get("PG_MAINTENANCE_WORK_MEM", "1GB")
parallel_maintenance_workers = os.environ.get("PG_MAX_PARALLEL_MAINTENANCE_WORKERS", "2")
skip_fts_index = os.environ.get("PG_SKIP_FTS_INDEX", "0").lower() in {"1", "true", "yes"}
defer_postload_indexes = os.environ.get("PG_DEFER_POSTLOAD_INDEXES", "0").lower() in {"1", "true", "yes"}
deferred_schema_file = os.environ.get("PG_DEFERRED_SCHEMA_FILE", "")

schema_sql = Path(create_sql).read_text(encoding="utf-8").replace("__PG_TABLE__", table)
preload_sql, postload_sql = split_schema_sections(schema_sql)

conn = psycopg2.connect(host=host, port=int(port), user=user, dbname=db)
conn.autocommit = False
cur = conn.cursor()
cur.execute("SELECT set_config('synchronous_commit', 'off', false)")
execute_statements(cur, preload_sql)
conn.commit()
log(f"Importing {len(files)} files into {table}")

copy_sql = f"""COPY {table}
(
    event_time, biz_date, trace_id, session_id, observation_id, parent_observation_id,
    seq_no, type, status, app, environment, task_category, trace_archetype, model,
    tool_name, input, output, input_tokens, output_tokens, total_cost, latency_ms,
    tenant, payload
)
FROM STDIN WITH (FORMAT text)"""

buffer: list[str] = []
pending_rows = 0


def flush() -> int:
    row_count = len(buffer)
    if row_count == 0:
        return 0
    cur.copy_expert(copy_sql, io.StringIO("".join(buffer)))
    buffer.clear()
    return row_count


for file_index, file_path in enumerate(files, start=1):
    log(f"Import file {file_index}/{len(files)}: {Path(file_path).name}")
    for raw_line in iter_lines(file_path, pigz_bin, decompress_threads):
        line = raw_line.strip()
        if not line:
            continue
        row = json.loads(line)
        values = (
            row["event_time"],
            row["biz_date"],
            row["trace_id"],
            row["session_id"],
            row["observation_id"],
            row["parent_observation_id"],
            row["seq_no"],
            row["type"],
            row["status"],
            row["app"],
            row["environment"],
            row["task_category"],
            row["trace_archetype"],
            row["model"],
            row["tool_name"],
            row["input"],
            row["output"],
            row["input_tokens"],
            row["output_tokens"],
            row["total_cost"],
            row["latency_ms"],
            row["tenant"],
            json.dumps(row["payload"], ensure_ascii=False, separators=(",", ":")),
        )
        buffer.append("\t".join(copy_escape(value) for value in values) + "\n")
        if len(buffer) >= copy_batch_rows:
            pending_rows += flush()
            if pending_rows >= copy_commit_rows:
                conn.commit()
                pending_rows = 0
    log(f"Import file {file_index}/{len(files)} complete")

pending_rows += flush()
if pending_rows:
    conn.commit()

postload_statements = collect_statements(postload_sql)
deferred_statements: list[str] = []
cur.execute("SELECT set_config('maintenance_work_mem', %s, false)", (maintenance_work_mem,))
cur.execute(
    "SELECT set_config('max_parallel_maintenance_workers', %s, false)",
    (parallel_maintenance_workers,),
)
for statement in postload_statements:
    upper = statement.upper()
    if defer_postload_indexes and (
        upper.startswith("CREATE INDEX")
        or upper.startswith("CREATE UNIQUE INDEX")
        or upper.startswith("ANALYZE ")
    ):
        deferred_statements.append(statement)
        continue
    if skip_fts_index and "IDX___PG_TABLE___FTS" in upper:
        deferred_statements.append(statement)
        continue
    cur.execute(statement)
conn.commit()

if deferred_schema_file:
    deferred_path = Path(deferred_schema_file)
    deferred_path.parent.mkdir(parents=True, exist_ok=True)
    if deferred_statements:
        deferred_path.write_text(";\n".join(deferred_statements) + ";\n", encoding="utf-8")
    elif deferred_path.exists():
        deferred_path.unlink()

cur.close()
conn.close()
PY

benchmark_log "postgres" "Import complete"
