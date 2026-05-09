#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${RUNTIME_DIR:-${SCRIPT_DIR}/runtime}"
ENV_FILE="${RUNTIME_DIR}/deploy.env"

DORIS_HOME="${DORIS_HOME:-${SCRIPT_DIR}/.local/apache-doris-4.1.0-rc01-bin-x64}"
DORIS_FE_HOST="${DORIS_FE_HOST:-127.0.0.1}"
DORIS_QUERY_PORT="${DORIS_QUERY_PORT:-19030}"
DORIS_HTTP_PORT="${DORIS_HTTP_PORT:-18030}"
DORIS_FE_EDIT_LOG_PORT="${DORIS_FE_EDIT_LOG_PORT:-19010}"
DORIS_FE_RPC_PORT="${DORIS_FE_RPC_PORT:-19020}"
DORIS_BE_HEARTBEAT_PORT="${DORIS_BE_HEARTBEAT_PORT:-19050}"
DORIS_BE_PORT="${DORIS_BE_PORT:-19060}"
DORIS_BE_WEB_PORT="${DORIS_BE_WEB_PORT:-18040}"
DORIS_BE_BRPC_PORT="${DORIS_BE_BRPC_PORT:-19070}"
DORIS_USER="${DORIS_USER:-root}"
DORIS_PASSWORD="${DORIS_PASSWORD:-}"
DORIS_DB="${DORIS_DB:-agentlogsbench_bench}"

resolve_java_home() {
    if [ -n "${JAVA_HOME:-}" ] && [ -x "${JAVA_HOME}/bin/java" ]; then
        printf '%s\n' "${JAVA_HOME}"
        return 0
    fi

    if [ -x "${DORIS_HOME}/jdk/bin/java" ]; then
        printf '%s\n' "${DORIS_HOME}/jdk"
        return 0
    fi

    for candidate in \
        /usr/lib/jvm/java-17-openjdk-amd64 \
        /usr/lib/jvm/java-17-openjdk \
        /usr/lib/jvm/temurin-17-jdk-amd64 \
        /usr/lib/jvm/temurin-17-jdk
    do
        if [ -x "${candidate}/bin/java" ]; then
            printf '%s\n' "${candidate}"
            return 0
        fi
    done

    if command -v update-alternatives >/dev/null 2>&1; then
        while read -r java_path; do
            if [ -n "${java_path}" ] && [ -x "${java_path}" ] && "${java_path}" -version 2>&1 | grep -q '"17\.'; then
                dirname "$(dirname "${java_path}")"
                return 0
            fi
        done < <(update-alternatives --list java 2>/dev/null || true)
    fi

    if command -v java >/dev/null 2>&1; then
        local java_bin
        java_bin="$(readlink -f "$(command -v java)")"
        dirname "$(dirname "${java_bin}")"
        return 0
    fi

    return 1
}

ensure_vm_max_map_count() {
    local required=2000000
    local current
    current="$(sysctl -n vm.max_map_count 2>/dev/null || echo 0)"
    if [ "${current}" -ge "${required}" ]; then
        return 0
    fi

    local sudo_cmd=()
    if [ "$(id -u)" -ne 0 ]; then
        if ! command -v sudo >/dev/null 2>&1 || ! sudo -n true >/dev/null 2>&1; then
            echo "Set kernel parameter 'vm.max_map_count' to a value greater than ${required}, example: 'sysctl -w vm.max_map_count=${required}'" >&2
            return 1
        fi
        sudo_cmd=(sudo -n)
    fi

    "${sudo_cmd[@]}" sysctl -w vm.max_map_count="${required}" >/dev/null
}

mkdir -p "${RUNTIME_DIR}"
ensure_vm_max_map_count

mysql_env=()
if [ -n "${DORIS_PASSWORD}" ]; then
    mysql_env=("MYSQL_PWD=${DORIS_PASSWORD}")
fi

if env "${mysql_env[@]}" mysql -h "${DORIS_FE_HOST}" -P "${DORIS_QUERY_PORT}" -u "${DORIS_USER}" -e "SELECT 1;" >/dev/null 2>&1; then
    alive="$(
        env "${mysql_env[@]}" mysql --batch -h "${DORIS_FE_HOST}" -P "${DORIS_QUERY_PORT}" -u "${DORIS_USER}" -N \
            -e "SHOW BACKENDS;" 2>/dev/null | awk -F '\t' 'NR == 1 {print $10}' || true
    )"
    if [ "${alive}" = "true" ] || [ "${alive}" = "1" ]; then
        cat > "${ENV_FILE}" <<EOF
export DORIS_FE_HOST="${DORIS_FE_HOST}"
export DORIS_QUERY_PORT="${DORIS_QUERY_PORT}"
export DORIS_HTTP_PORT="${DORIS_HTTP_PORT}"
export DORIS_USER="${DORIS_USER}"
export DORIS_PASSWORD="${DORIS_PASSWORD}"
export DORIS_HOME="${DORIS_HOME}"
export JAVA_HOME="${JAVA_HOME:-}"
export DORIS_LOCAL=1
EOF
        echo "[doris] deploy reuse existing runtime"
        exit 0
    fi
fi

if [ -f "${SCRIPT_DIR}/install.sh" ]; then
    DORIS_HOME="${DORIS_HOME}" bash "${SCRIPT_DIR}/install.sh"
fi

if [ ! -x "${DORIS_HOME}/fe/bin/start_fe.sh" ] || [ ! -x "${DORIS_HOME}/be/bin/start_be.sh" ]; then
    echo "Doris binaries not found in ${DORIS_HOME}" >&2
    exit 1
fi

JAVA_HOME="${JAVA_HOME:-$(resolve_java_home || true)}"

if [ -z "${JAVA_HOME}" ]; then
    echo "JAVA_HOME is required for Doris" >&2
    exit 1
fi

# Doris FE/BE startup scripts require a much higher open-file limit than the default shell.
ulimit -n 655350 >/dev/null 2>&1 || true

for port in \
    "${DORIS_QUERY_PORT}" "${DORIS_HTTP_PORT}" "${DORIS_FE_EDIT_LOG_PORT}" "${DORIS_FE_RPC_PORT}" \
    "${DORIS_BE_HEARTBEAT_PORT}" "${DORIS_BE_PORT}" "${DORIS_BE_WEB_PORT}" "${DORIS_BE_BRPC_PORT}"
do
    if ss -ltnp | grep -q ":${port} "; then
        pids="$(ss -ltnp | grep ":${port} " | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | sort -u)"
        for pid in ${pids}; do
            kill "${pid}" >/dev/null 2>&1 || true
        done
    fi
done

sleep 1

mkdir -p "${RUNTIME_DIR}/fe-meta" "${RUNTIME_DIR}/fe-log" "${RUNTIME_DIR}/be-storage" "${RUNTIME_DIR}/be-log"

cp "${DORIS_HOME}/fe/conf/fe.conf.template" "${DORIS_HOME}/fe/conf/fe.conf" 2>/dev/null \
    || [ -f "${DORIS_HOME}/fe/conf/fe.conf" ] || touch "${DORIS_HOME}/fe/conf/fe.conf"

sed -i '/^# --- agentlogsbench doris ---$/,/^# --- end agentlogsbench doris ---$/d' "${DORIS_HOME}/fe/conf/fe.conf"
cat >> "${DORIS_HOME}/fe/conf/fe.conf" <<EOF
# --- agentlogsbench doris ---
priority_networks = ${DORIS_FE_HOST}/32
meta_dir = ${RUNTIME_DIR}/fe-meta
sys_log_dir = ${RUNTIME_DIR}/fe-log
edit_log_port = ${DORIS_FE_EDIT_LOG_PORT}
http_port = ${DORIS_HTTP_PORT}
query_port = ${DORIS_QUERY_PORT}
rpc_port = ${DORIS_FE_RPC_PORT}
arrow_flight_sql_port = 19040
# --- end agentlogsbench doris ---
EOF

sed -i '/^# --- agentlogsbench doris ---$/,/^# --- end agentlogsbench doris ---$/d' "${DORIS_HOME}/be/conf/be.conf"
cat >> "${DORIS_HOME}/be/conf/be.conf" <<EOF
# --- agentlogsbench doris ---
priority_networks = ${DORIS_FE_HOST}/32
storage_root_path = ${RUNTIME_DIR}/be-storage
sys_log_dir = ${RUNTIME_DIR}/be-log
heartbeat_service_port = ${DORIS_BE_HEARTBEAT_PORT}
be_port = ${DORIS_BE_PORT}
webserver_port = ${DORIS_BE_WEB_PORT}
brpc_port = ${DORIS_BE_BRPC_PORT}
# --- end agentlogsbench doris ---
EOF

JAVA_HOME="${JAVA_HOME}" "${DORIS_HOME}/be/bin/start_be.sh" --daemon
JAVA_HOME="${JAVA_HOME}" "${DORIS_HOME}/fe/bin/start_fe.sh" --daemon

for _ in $(seq 1 120); do
    if env "${mysql_env[@]}" mysql -h "${DORIS_FE_HOST}" -P "${DORIS_QUERY_PORT}" -u "${DORIS_USER}" -e "SHOW FRONTENDS;" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

env "${mysql_env[@]}" mysql -h "${DORIS_FE_HOST}" -P "${DORIS_QUERY_PORT}" -u "${DORIS_USER}" \
    -e "ALTER SYSTEM ADD BACKEND \"${DORIS_FE_HOST}:${DORIS_BE_HEARTBEAT_PORT}\";" >/dev/null 2>&1 || true

for _ in $(seq 1 60); do
    alive="$(
        env "${mysql_env[@]}" mysql --batch -h "${DORIS_FE_HOST}" -P "${DORIS_QUERY_PORT}" -u "${DORIS_USER}" -N \
            -e "SHOW BACKENDS;" 2>/dev/null | awk -F '\t' 'NR == 1 {print $10}' || true
    )"
    if [ "${alive}" = "true" ] || [ "${alive}" = "1" ]; then
        break
    fi
    sleep 1
done

alive="$(
    env "${mysql_env[@]}" mysql --batch -h "${DORIS_FE_HOST}" -P "${DORIS_QUERY_PORT}" -u "${DORIS_USER}" -N \
        -e "SHOW BACKENDS;" 2>/dev/null | awk -F '\t' 'NR == 1 {print $10}' || true
)"
if [ "${alive}" != "true" ] && [ "${alive}" != "1" ]; then
    echo "Doris backend did not become alive on ${DORIS_FE_HOST}:${DORIS_BE_HEARTBEAT_PORT}" >&2
    exit 1
fi

probe_sql="
CREATE DATABASE IF NOT EXISTS ${DORIS_DB};
DROP TABLE IF EXISTS ${DORIS_DB}.__agentlogsbench_deploy_probe__;
CREATE TABLE ${DORIS_DB}.__agentlogsbench_deploy_probe__ (
    probe_id INT
)
ENGINE=OLAP
DUPLICATE KEY(probe_id)
DISTRIBUTED BY RANDOM BUCKETS 1
PROPERTIES('replication_num' = '1');
DROP TABLE IF EXISTS ${DORIS_DB}.__agentlogsbench_deploy_probe__;
"

for _ in $(seq 1 30); do
    if env "${mysql_env[@]}" mysql -h "${DORIS_FE_HOST}" -P "${DORIS_QUERY_PORT}" -u "${DORIS_USER}" \
        -e "${probe_sql}" >/dev/null 2>&1; then
        break
    fi
    sleep 2
done

if ! env "${mysql_env[@]}" mysql -h "${DORIS_FE_HOST}" -P "${DORIS_QUERY_PORT}" -u "${DORIS_USER}" \
    -e "${probe_sql}" >/dev/null 2>&1; then
    echo "Doris backend became alive, but is not yet ready to create OLAP tables on ${DORIS_FE_HOST}:${DORIS_BE_HEARTBEAT_PORT}" >&2
    exit 1
fi

cat > "${ENV_FILE}" <<EOF
export DORIS_FE_HOST="${DORIS_FE_HOST}"
export DORIS_QUERY_PORT="${DORIS_QUERY_PORT}"
export DORIS_HTTP_PORT="${DORIS_HTTP_PORT}"
export DORIS_USER="${DORIS_USER}"
export DORIS_PASSWORD="${DORIS_PASSWORD}"
export DORIS_HOME="${DORIS_HOME}"
export JAVA_HOME="${JAVA_HOME}"
export DORIS_LOCAL=1
EOF

echo "[doris] deploy done"
