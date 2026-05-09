#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/runtime_env.sh"

RUNTIME_DIR="${RUNTIME_DIR:-${SCRIPT_DIR}/runtime}"
PG_USER="${PG_USER:-postgres}"
PG_DB="${PG_DB:-agentlogsbench_pg}"
PGDATA="${PGDATA:-${RUNTIME_DIR}/pgdata}"
PG_LOG="${PG_LOG:-${RUNTIME_DIR}/postgres.log}"
PG_HOST="${PG_HOST:-127.0.0.1}"
PG_PORT="$(resolve_pg_port "${PG_PORT:-}")"
PG_OS_USER="${PG_OS_USER:-agentlogsbenchpg}"
default_pg_total_memory_mb() {
    local total_kb

    if [ -r /proc/meminfo ]; then
        total_kb="$(awk '/MemTotal:/ { print $2 }' /proc/meminfo)"
    else
        total_kb=""
    fi

    if [ -z "${total_kb}" ]; then
        echo 4096
        return 0
    fi

    echo "$((total_kb / 1024))"
}

default_pg_shared_buffers() {
    local total_mb
    local shared_mb

    total_mb="$(default_pg_total_memory_mb)"
    shared_mb="$((total_mb / 32))"

    if [ "${shared_mb}" -lt 128 ]; then
        shared_mb=128
    fi
    if [ "${shared_mb}" -gt 4096 ]; then
        shared_mb=4096
    fi

    echo "${shared_mb}MB"
}

default_pg_effective_cache_size() {
    local total_mb
    local cache_mb

    total_mb="$(default_pg_total_memory_mb)"
    cache_mb="$((total_mb / 8))"

    if [ "${cache_mb}" -lt 512 ]; then
        cache_mb=512
    fi
    if [ "${cache_mb}" -gt 16384 ]; then
        cache_mb=16384
    fi

    echo "${cache_mb}MB"
}

default_pg_maintenance_work_mem() {
    local total_mb
    local work_mem_mb

    total_mb="$(default_pg_total_memory_mb)"
    work_mem_mb="$((total_mb / 64))"

    if [ "${work_mem_mb}" -lt 64 ]; then
        work_mem_mb=64
    fi
    if [ "${work_mem_mb}" -gt 1024 ]; then
        work_mem_mb=1024
    fi

    echo "${work_mem_mb}MB"
}

default_pg_parallel_workers() {
    local cpu_count

    cpu_count="$(getconf _NPROCESSORS_ONLN 2>/dev/null || true)"
    if [ -z "${cpu_count}" ] || [ "${cpu_count}" -lt 1 ] 2>/dev/null; then
        cpu_count=2
    fi
    if [ "${cpu_count}" -gt 8 ]; then
        cpu_count=8
    fi

    echo "${cpu_count}"
}

default_pg_parallel_maintenance_workers() {
    local cpu_count
    local worker_count

    cpu_count="$(default_pg_parallel_workers)"
    worker_count="$((cpu_count / 2))"
    if [ "${worker_count}" -lt 1 ]; then
        worker_count=1
    fi
    if [ "${worker_count}" -gt 4 ]; then
        worker_count=4
    fi

    echo "${worker_count}"
}

PG_SHARED_BUFFERS="${PG_SHARED_BUFFERS:-$(default_pg_shared_buffers)}"
PG_EFFECTIVE_CACHE_SIZE="${PG_EFFECTIVE_CACHE_SIZE:-$(default_pg_effective_cache_size)}"
PG_MAINTENANCE_WORK_MEM="${PG_MAINTENANCE_WORK_MEM:-$(default_pg_maintenance_work_mem)}"
PG_MAX_WAL_SIZE="${PG_MAX_WAL_SIZE:-16GB}"
PG_CHECKPOINT_TIMEOUT="${PG_CHECKPOINT_TIMEOUT:-1h}"
PG_CHECKPOINT_COMPLETION_TARGET="${PG_CHECKPOINT_COMPLETION_TARGET:-0.9}"
PG_MAX_PARALLEL_WORKERS="${PG_MAX_PARALLEL_WORKERS:-$(default_pg_parallel_workers)}"
PG_MAX_PARALLEL_MAINTENANCE_WORKERS="${PG_MAX_PARALLEL_MAINTENANCE_WORKERS:-$(default_pg_parallel_maintenance_workers)}"

if [ -z "${PG_BIN_DIR:-}" ]; then
    PG_BIN_DIR="$(resolve_pg_bin_dir || true)"
fi

db_is_ready() {
    if ! python_can_import_psycopg2; then
        return 1
    fi
    run_python_with_pgclient - "${PG_HOST}" "${PG_PORT}" "${PG_USER}" "${PG_DB}" <<'PY' >/dev/null 2>&1
import sys
import psycopg2

host, port, user, db = sys.argv[1:5]
conn = psycopg2.connect(host=host, port=int(port), user=user, dbname=db)
conn.autocommit = True
cur = conn.cursor()
cur.execute("SELECT 1")
cur.close()
conn.close()
PY
}

cluster_running() {
    [ -n "${PG_CTL:-}" ] && [ -x "${PG_CTL}" ] && [ -d "${PGDATA}" ] && "${PG_CTL}" -D "${PGDATA}" status >/dev/null 2>&1
}

print_start_failure_log() {
    if [ -f "${PG_LOG}" ]; then
        echo "PostgreSQL start failed; tail of ${PG_LOG}:" >&2
        tail -n 80 "${PG_LOG}" >&2 || true
    else
        echo "PostgreSQL start failed and no log was written to ${PG_LOG}" >&2
    fi
}

configure_postgresql_conf() {
    local conf_file="${PGDATA}/postgresql.conf"
    sed -i '/^# --- agentlogsbench postgres ---$/,/^# --- end agentlogsbench postgres ---$/d' "${conf_file}"
    cat >> "${conf_file}" <<EOF
# --- agentlogsbench postgres ---
listen_addresses = '${PG_HOST}'
port = ${PG_PORT}
unix_socket_directories = '${RUNTIME_DIR}'
shared_buffers = '${PG_SHARED_BUFFERS}'
effective_cache_size = '${PG_EFFECTIVE_CACHE_SIZE}'
maintenance_work_mem = '${PG_MAINTENANCE_WORK_MEM}'
fsync = off
synchronous_commit = off
full_page_writes = off
wal_level = minimal
max_wal_size = '${PG_MAX_WAL_SIZE}'
checkpoint_timeout = '${PG_CHECKPOINT_TIMEOUT}'
checkpoint_completion_target = ${PG_CHECKPOINT_COMPLETION_TARGET}
max_wal_senders = 0
autovacuum = off
jit = off
max_worker_processes = ${PG_MAX_PARALLEL_WORKERS}
max_parallel_workers = ${PG_MAX_PARALLEL_WORKERS}
max_parallel_maintenance_workers = ${PG_MAX_PARALLEL_MAINTENANCE_WORKERS}
# --- end agentlogsbench postgres ---
EOF
}

ensure_db_exists() {
    if [ "$("${PSQL_BIN}" -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '${PG_DB}'")" = "1" ]; then
        return 0
    fi

    "${CREATEDB}" -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" "${PG_DB}"
}

if db_is_ready; then
    echo "[postgres] deploy reuse existing runtime"
    exit 0
fi

bash "${SCRIPT_DIR}/install.sh"
PG_BIN_DIR="$(resolve_pg_bin_dir)"
PG_HOME="${PG_HOME:-$(cd "${PG_BIN_DIR}/.." && pwd)}"
PG_CTL="${PG_CTL:-${PG_BIN_DIR}/pg_ctl}"
INITDB="${INITDB:-${PG_BIN_DIR}/initdb}"
CREATEDB="${CREATEDB:-${PG_BIN_DIR}/createdb}"
PG_RUN="${PG_RUN:-${PG_BIN_DIR}/postgres}"
PSQL_BIN="${PSQL_BIN:-${PG_BIN_DIR}/psql}"
PG_CLIENT_DIR="${PG_CLIENT_DIR:-$(resolve_pg_client_dir || true)}"

if tcp_port_in_use "${PG_PORT}"; then
    echo "Port ${PG_PORT} is already in use and ${PG_HOST}:${PG_PORT}/${PG_DB} is not ready" >&2
    exit 1
fi

if [ "$(id -u)" -eq 0 ]; then
    if ! id "${PG_OS_USER}" >/dev/null 2>&1; then
        useradd -m -r -s /bin/bash "${PG_OS_USER}"
    fi

    mkdir -p "${RUNTIME_DIR}" "$(dirname "${PGDATA}")" "$(dirname "${PG_LOG}")"
    chown -R "${PG_OS_USER}:${PG_OS_USER}" "${RUNTIME_DIR}"
    chmod -R a+rX "${PG_HOME}" || true
    if [ -n "${PG_CLIENT_DIR}" ] && [ -d "${PG_CLIENT_DIR}" ]; then
        chmod -R a+rX "${PG_CLIENT_DIR}" || true
    fi

    temp_script="$(mktemp /tmp/postgres-deploy-XXXX.sh)"
    cat > "${temp_script}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export PG_BIN_DIR="${PG_BIN_DIR}"
export PG_CTL="${PG_CTL}"
export INITDB="${INITDB}"
export CREATEDB="${CREATEDB}"
export PSQL_BIN="${PSQL_BIN}"
export PG_USER="${PG_USER}"
export PG_DB="${PG_DB}"
export PGDATA="${PGDATA}"
export PG_LOG="${PG_LOG}"
export PG_HOST="${PG_HOST}"
export PG_PORT="${PG_PORT}"
export RUNTIME_DIR="${RUNTIME_DIR}"
export PG_SHARED_BUFFERS="${PG_SHARED_BUFFERS}"
export PG_EFFECTIVE_CACHE_SIZE="${PG_EFFECTIVE_CACHE_SIZE}"
export PG_MAINTENANCE_WORK_MEM="${PG_MAINTENANCE_WORK_MEM}"
export PG_MAX_WAL_SIZE="${PG_MAX_WAL_SIZE}"
export PG_CHECKPOINT_TIMEOUT="${PG_CHECKPOINT_TIMEOUT}"
export PG_CHECKPOINT_COMPLETION_TARGET="${PG_CHECKPOINT_COMPLETION_TARGET}"
export PG_MAX_PARALLEL_WORKERS="${PG_MAX_PARALLEL_WORKERS}"
export PG_MAX_PARALLEL_MAINTENANCE_WORKERS="${PG_MAX_PARALLEL_MAINTENANCE_WORKERS}"

mkdir -p "${RUNTIME_DIR}" "$(dirname "${PGDATA}")" "$(dirname "${PG_LOG}")"

if [ ! -s "${PGDATA}/PG_VERSION" ]; then
    "${INITDB}" -D "${PGDATA}" --auth=trust --username="${PG_USER}" >/dev/null
fi

sed -i '/^# --- agentlogsbench postgres ---$/,/^# --- end agentlogsbench postgres ---$/d' "${PGDATA}/postgresql.conf"
cat >> "${PGDATA}/postgresql.conf" <<CONF
# --- agentlogsbench postgres ---
listen_addresses = '${PG_HOST}'
port = ${PG_PORT}
unix_socket_directories = '${RUNTIME_DIR}'
shared_buffers = '${PG_SHARED_BUFFERS}'
effective_cache_size = '${PG_EFFECTIVE_CACHE_SIZE}'
maintenance_work_mem = '${PG_MAINTENANCE_WORK_MEM}'
fsync = off
synchronous_commit = off
full_page_writes = off
wal_level = minimal
max_wal_size = '${PG_MAX_WAL_SIZE}'
checkpoint_timeout = '${PG_CHECKPOINT_TIMEOUT}'
checkpoint_completion_target = ${PG_CHECKPOINT_COMPLETION_TARGET}
max_wal_senders = 0
autovacuum = off
jit = off
max_worker_processes = ${PG_MAX_PARALLEL_WORKERS}
max_parallel_workers = ${PG_MAX_PARALLEL_WORKERS}
max_parallel_maintenance_workers = ${PG_MAX_PARALLEL_MAINTENANCE_WORKERS}
# --- end agentlogsbench postgres ---
CONF

if ! "${PG_CTL}" -D "${PGDATA}" status >/dev/null 2>&1; then
    if ! "${PG_CTL}" -D "${PGDATA}" -l "${PG_LOG}" -o "-h ${PG_HOST} -p ${PG_PORT}" -w start; then
        if [ -f "${PG_LOG}" ]; then
            echo "PostgreSQL start failed; tail of ${PG_LOG}:" >&2
            tail -n 80 "${PG_LOG}" >&2 || true
        else
            echo "PostgreSQL start failed and no log was written to ${PG_LOG}" >&2
        fi
        exit 1
    fi
fi
EOF
    chmod 700 "${temp_script}"
    chown "${PG_OS_USER}:${PG_OS_USER}" "${temp_script}"
    su -s /bin/bash "${PG_OS_USER}" -c "${temp_script}"
    rm -f "${temp_script}"
else
    mkdir -p "${RUNTIME_DIR}" "$(dirname "${PGDATA}")" "$(dirname "${PG_LOG}")"
    if [ ! -s "${PGDATA}/PG_VERSION" ]; then
        "${INITDB}" -D "${PGDATA}" --auth=trust --username="${PG_USER}" >/dev/null
    fi
    configure_postgresql_conf
    if ! cluster_running; then
        if ! "${PG_CTL}" -D "${PGDATA}" -l "${PG_LOG}" -o "-h ${PG_HOST} -p ${PG_PORT}" -w start; then
            print_start_failure_log
            exit 1
        fi
    fi
fi

ensure_db_exists

for _ in $(seq 1 30); do
    if db_is_ready; then
        echo "[postgres] deploy done"
        exit 0
    fi
    sleep 1
done

echo "PostgreSQL did not become ready on ${PG_HOST}:${PG_PORT}/${PG_DB}" >&2
exit 1
