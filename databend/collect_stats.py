#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTLOGSBENCH_ROOT = REPO_ROOT / "agentlogsbench"
DEFAULT_DRIVER_PATH = AGENTLOGSBENCH_ROOT / "bendsql" / "bindings" / "python" / "package"


def add_driver_path(driver_path: Path, explicit: bool) -> None:
    has_extension = any((driver_path / "databend_driver").glob("_databend_driver*.so"))
    if (explicit or has_extension) and str(driver_path) not in sys.path:
        sys.path.insert(0, str(driver_path))


def int_or_zero(value: Any) -> int:
    return int(value) if value is not None else 0


def compute_storage_sizes(table_values: tuple[Any, ...] | None) -> tuple[int, int]:
    if table_values is None:
        return 0, 0

    (
        _num_rows,
        data_size_raw,
        data_compressed_size,
        index_size_raw,
        bloom_index_size,
        ngram_index_size,
        inverted_index_size,
        vector_index_size,
        virtual_column_size,
    ) = table_values
    data_size = int_or_zero(data_compressed_size) or int_or_zero(data_size_raw)
    component_index_size = (
        int_or_zero(bloom_index_size)
        + int_or_zero(ngram_index_size)
        + int_or_zero(inverted_index_size)
        + int_or_zero(vector_index_size)
        + int_or_zero(virtual_column_size)
    )
    index_size = max(int_or_zero(index_size_raw), component_index_size)
    return data_size, index_size


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect Databend row count and storage statistics.")
    parser.add_argument("--dsn", default=os.environ.get("DATABEND_DSN", "databend://root:@127.0.0.1:8000/?sslmode=disable"))
    explicit_driver_path = "DATABEND_DRIVER_PYTHONPATH" in os.environ
    parser.add_argument("--driver-path", type=Path, default=Path(os.environ.get("DATABEND_DRIVER_PYTHONPATH", DEFAULT_DRIVER_PATH)))
    parser.add_argument("--database", required=True)
    parser.add_argument("--table", required=True)
    parser.add_argument("--count-file", type=Path, required=True)
    parser.add_argument("--total-size-file", type=Path, required=True)
    parser.add_argument("--data-size-file", type=Path, required=True)
    parser.add_argument("--index-size-file", type=Path, required=True)
    args = parser.parse_args()

    add_driver_path(args.driver_path, explicit_driver_path)
    try:
        import databend_driver
    except ImportError as exc:
        raise SystemExit(f"Could not import databend_driver from {args.driver_path}: {exc}") from exc

    client = databend_driver.BlockingDatabendClient(args.dsn)
    conn = client.get_conn()
    try:
        count_row = conn.query_row(
            f"SELECT COUNT(*) FROM {args.database}.{args.table}"
        )
        table_row = conn.query_row(
            """
            SELECT
              num_rows,
              data_size,
              data_compressed_size,
              index_size,
              bloom_index_size,
              ngram_index_size,
              inverted_index_size,
              vector_index_size,
              virtual_column_size
            FROM system.tables
            WHERE database = ? AND name = ?
            """,
            (args.database, args.table),
        )
    finally:
        conn.close()

    row_count = int(count_row.values()[0]) if count_row is not None else 0
    data_size, index_size = compute_storage_sizes(table_row.values() if table_row is not None else None)

    total_size = data_size + index_size

    args.count_file.write_text(f"{row_count}\n", encoding="utf-8")
    args.total_size_file.write_text(f"{total_size}\n", encoding="utf-8")
    args.data_size_file.write_text(f"{data_size}\n", encoding="utf-8")
    args.index_size_file.write_text(f"{index_size}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
