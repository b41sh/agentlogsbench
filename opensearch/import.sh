#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${ROOT_DIR}/agentlogsbench/common/benchmark_lib.sh"

OS_ENDPOINT="${OS_ENDPOINT:-http://127.0.0.1:9200}"
OS_INDEX="${OS_INDEX:-agentlogsbench_agent_observations}"
DATA_GLOB="${DATA_GLOB:-${ROOT_DIR}/agentlogsbench/common/generated/small/agent_observations_s.ndjson}"
CREATE_JSON="${CREATE_JSON:-${SCRIPT_DIR}/create.json}"

shopt -s nullglob
files=( ${DATA_GLOB} )
shopt -u nullglob

if [ "${#files[@]}" -eq 0 ]; then
    echo "No files matched DATA_GLOB=${DATA_GLOB}" >&2
    exit 1
fi

benchmark_log "opensearch" "Resetting index ${OS_INDEX}"
curl -sS -X DELETE "${OS_ENDPOINT}/${OS_INDEX}" >/dev/null || true

python3 - "${OS_ENDPOINT}" "${OS_INDEX}" "${CREATE_JSON}" "${files[@]}" <<'PY'
import gzip
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from typing import Iterator
from pathlib import Path
from urllib import request

endpoint, index_name, create_json, *files = sys.argv[1:]
mapping = json.loads(Path(create_json).read_text(encoding="utf-8"))
BULK_MAX_BYTES = 32 * 1024 * 1024
BULK_MAX_ACTIONS = 20000
BULK_ACTION = b'{"index":{}}\n'
decompress_threads = os.environ.get("OS_DECOMPRESS_THREADS", "1")
pigz_bin = shutil.which("pigz")


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [opensearch] {message}", file=sys.stderr, flush=True)


def call(method, url, payload=None, timeout=120):
    data = None
    headers = {}
    if payload is not None:
        if isinstance(payload, (bytes, bytearray)):
            data = bytes(payload)
        else:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
    req = request.Request(url, data=data, headers=headers, method=method)
    with request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body) if body else {}


call("PUT", f"{endpoint}/{index_name}", mapping, timeout=120)


def post_bulk(payload):
    if not payload:
        return
    req = request.Request(
        f"{endpoint}/{index_name}/_bulk?filter_path=errors,items.*.error",
        data=payload,
        headers={"Content-Type": "application/x-ndjson; charset=utf-8"},
        method="POST",
    )
    with request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if result.get("errors"):
        raise SystemExit(result)


def iter_lines(file_path: str) -> Iterator[bytes]:
    if file_path.endswith(".gz") and pigz_bin:
        proc = subprocess.Popen(
            [pigz_bin, "-dc", "-p", decompress_threads, file_path],
            stdout=subprocess.PIPE,
        )
        if proc.stdout is None:
            raise SystemExit(f"Unable to stream {file_path} with pigz")
        try:
            for raw_line in proc.stdout:
                yield raw_line
        finally:
            proc.stdout.close()
            if proc.wait() != 0:
                raise SystemExit(f"pigz failed while reading {file_path}")
        return

    if file_path.endswith(".gz"):
        opener = gzip.open
    else:
        opener = open
    with opener(file_path, "rb") as handle:
        for raw_line in handle:
            yield raw_line


log(
    f"Importing {len(files)} files into {index_name} with serial bulk uploads decompress_threads={decompress_threads}"
)
for file_index, file_path in enumerate(files, start=1):
    log(f"Import file {file_index}/{len(files)}: {Path(file_path).name}")
    bulk = bytearray()
    bulk_actions = 0
    bulk_requests = 0
    for raw_line in iter_lines(file_path):
        line = raw_line.rstrip(b"\r\n")
        if not line:
            continue
        bulk.extend(BULK_ACTION)
        bulk.extend(line)
        bulk.extend(b"\n")
        bulk_actions += 1
        if len(bulk) >= BULK_MAX_BYTES or bulk_actions >= BULK_MAX_ACTIONS:
            post_bulk(bytes(bulk))
            bulk_requests += 1
            bulk = bytearray()
            bulk_actions = 0
    if bulk:
        post_bulk(bytes(bulk))
        bulk_requests += 1
    log(f"Import file {file_index}/{len(files)} complete bulk_requests={bulk_requests}")

call("POST", f"{endpoint}/{index_name}/_refresh", timeout=60)
PY

benchmark_log "opensearch" "Import complete"
