#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTLOGSBENCH_ROOT = REPO_ROOT / "agentlogsbench"
DEFAULT_DRIVER_PATH = AGENTLOGSBENCH_ROOT / "bendsql" / "bindings" / "python" / "package"


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [databend] {message}", file=sys.stderr)


def add_driver_path(driver_path: Path, explicit: bool) -> None:
    has_extension = any((driver_path / "databend_driver").glob("_databend_driver*.so"))
    if (explicit or has_extension) and str(driver_path) not in sys.path:
        sys.path.insert(0, str(driver_path))


def render_create_sql(path: Path, database: str, table: str) -> str:
    return (
        path.read_text(encoding="utf-8")
        .replace("__DATABEND_DB__", database)
        .replace("__DATABEND_TABLE__", table)
    )


def iter_statements(sql_text: str) -> Iterable[str]:
    for statement in sql_text.split(";"):
        stripped = statement.strip()
        if stripped:
            yield stripped


def expand_files(patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        for token in pattern.split():
            matched = sorted(Path(path) for path in glob.glob(token)) if any(char in token for char in "*?[") else [Path(token)]
            files.extend(path for path in matched if path.exists())
    return files


def load_file(conn: object, table: str, file_path: Path, method: str) -> int:
    sql = f"INSERT INTO {table} VALUES"
    format_options = {"type": "ndjson"}
    if file_path.suffix == ".gz":
        format_options["compression"] = "gzip"

    stats = conn.load_file(sql, str(file_path), method, format_options, None)  # type: ignore[attr-defined]
    return int(getattr(stats, "write_rows", 0))


def recluster_table(conn: object, table: str) -> None:
    log(f"Reclustering table {table}")
    conn.exec(f"ALTER TABLE {table} RECLUSTER FINAL")  # type: ignore[attr-defined]
    log(f"Recluster complete for {table}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import agent observation NDJSON into Databend.")
    parser.add_argument("--dsn", default=os.environ.get("DATABEND_DSN", "databend://root:@127.0.0.1:8000/?sslmode=disable"))
    explicit_driver_path = "DATABEND_DRIVER_PYTHONPATH" in os.environ
    parser.add_argument("--driver-path", type=Path, default=Path(os.environ.get("DATABEND_DRIVER_PYTHONPATH", DEFAULT_DRIVER_PATH)))
    parser.add_argument("--database", default=os.environ.get("DATABEND_DB", "agentlogsbench_bench"))
    parser.add_argument("--table", default=os.environ.get("DATABEND_TABLE", "agent_observations"))
    parser.add_argument("--create-sql", type=Path, default=Path(__file__).with_name("create.sql"))
    parser.add_argument("--data-glob", action="append", default=[])
    parser.add_argument("--load-method", default=os.environ.get("DATABEND_LOAD_METHOD", "stage"), choices=("stage", "streaming"))
    parser.add_argument(
        "--recluster",
        action=argparse.BooleanOptionalAction,
        default=os.environ.get("DATABEND_RECLUSTER", "1").lower() not in {"0", "false", "no"},
    )
    parser.add_argument("--schema-only", action="store_true")
    args = parser.parse_args()

    add_driver_path(args.driver_path, explicit_driver_path)
    try:
        import databend_driver
    except ImportError as exc:
        raise SystemExit(f"Could not import databend_driver from {args.driver_path}: {exc}") from exc

    client = databend_driver.BlockingDatabendClient(args.dsn)
    conn = client.get_conn()
    try:
        log(f"Preparing schema {args.database}.{args.table}")
        for statement in iter_statements(render_create_sql(args.create_sql, args.database, args.table)):
            conn.exec(statement)

        if args.schema_only:
            log("Schema-only import requested; skipping data load")
            return 0

        files = expand_files(args.data_glob)
        if not files:
            raise SystemExit("No input files matched --data-glob")

        loaded_rows = 0
        for index, file_path in enumerate(files, start=1):
            log(f"Import file {index}/{len(files)}: {file_path.name}")
            loaded_rows += load_file(conn, args.table, file_path, args.load_method)
        table_rows = int(conn.query_row(f"SELECT COUNT(*) FROM {args.table}").values()[0])
        if table_rows != loaded_rows:
            raise SystemExit(f"Loaded row count mismatch: load_file wrote {loaded_rows}, table has {table_rows}")
        if args.recluster:
            recluster_table(conn, args.table)
        log(f"Import complete files={len(files)} rows={loaded_rows}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
