#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${ROOT_DIR}/agentlogsbench/common/benchmark_lib.sh"

RUNTIME_DIR="${RUNTIME_DIR:-${SCRIPT_DIR}/runtime}"
DATABEND_DSN="${DATABEND_DSN:-databend://root:@127.0.0.1:8000/?sslmode=disable}"
DEFAULT_DATABEND_DRIVER_PYTHONPATH="${ROOT_DIR}/agentlogsbench/bendsql/bindings/python/package"

mkdir -p "${RUNTIME_DIR}"

if [ -n "${DATABEND_DRIVER_PYTHONPATH:-}" ]; then
    export PYTHONPATH="${DATABEND_DRIVER_PYTHONPATH}${PYTHONPATH:+:${PYTHONPATH}}"
elif compgen -G "${DEFAULT_DATABEND_DRIVER_PYTHONPATH}/databend_driver/_databend_driver*.so" >/dev/null; then
    export PYTHONPATH="${DEFAULT_DATABEND_DRIVER_PYTHONPATH}${PYTHONPATH:+:${PYTHONPATH}}"
fi
export DATABEND_DSN

benchmark_log "databend" "Checking Databend connection via DATABEND_DSN=${DATABEND_DSN}"

python3 - <<'PY'
from __future__ import annotations

import os
import sys


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


try:
    import databend_driver
except ImportError as exc:
    fail(
        "Could not import databend_driver. Build or install the Python binding, "
        "or set DATABEND_DRIVER_PYTHONPATH to its package directory. "
        f"Import error: {exc}"
    )

dsn = os.environ["DATABEND_DSN"]
try:
    client = databend_driver.BlockingDatabendClient(dsn)
    conn = client.get_conn()
    try:
        version = conn.version()
        row = conn.query_row("SELECT 1")
        values = row.values()
        if values != (1,):
            fail(f"Databend health check returned unexpected row: {values!r}")
    finally:
        conn.close()
except Exception as exc:  # noqa: BLE001 - startup diagnostics should preserve driver error text.
    fail(f"Databend health check failed for DATABEND_DSN={dsn}: {exc}")

print(f"Databend connection ok; version={version}", file=sys.stderr)
PY

benchmark_log "databend" "Runtime ready in ${RUNTIME_DIR}"
