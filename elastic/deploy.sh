#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${RUNTIME_DIR:-${SCRIPT_DIR}/runtime}"

ES_ENDPOINT="${ES_ENDPOINT:-http://127.0.0.1:9200}"
ES_HOST="${ES_HOST:-127.0.0.1}"
ES_PORT="${ES_PORT:-9200}"
ES_VERSION="${ES_VERSION:-9.3.0}"
ES_BIN="${ES_BIN:-${SCRIPT_DIR}/.local/elasticsearch-${ES_VERSION}/bin/elasticsearch}"
ES_PID_FILE="${ES_PID_FILE:-${RUNTIME_DIR}/elasticsearch.pid}"
ES_CONF_DIR="${ES_CONF_DIR:-${RUNTIME_DIR}/conf}"
ES_STORAGE_PATH="${ES_STORAGE_PATH:-${RUNTIME_DIR}/data}"
ES_LOG_PATH="${ES_LOG_PATH:-${RUNTIME_DIR}/logs}"
ES_OS_USER="${ES_OS_USER:-agentlogsbenches}"

default_es_heap_mb() {
    local total_kb
    local total_mb
    local heap_mb

    if [ -r /proc/meminfo ]; then
        total_kb="$(awk '/MemTotal:/ { print $2 }' /proc/meminfo)"
    else
        total_kb=""
    fi

    if [ -z "${total_kb}" ]; then
        echo 1024
        return 0
    fi

    total_mb="$((total_kb / 1024))"
    heap_mb="$((total_mb / 16))"

    if [ "${heap_mb}" -lt 1024 ]; then
        heap_mb=1024
    fi
    if [ "${heap_mb}" -gt 8192 ]; then
        heap_mb=8192
    fi

    echo "${heap_mb}"
}

ES_HEAP_MB="${ES_HEAP_MB:-$(default_es_heap_mb)}"
ES_JAVA_OPTS="${ES_JAVA_OPTS:--Xms${ES_HEAP_MB}m -Xmx${ES_HEAP_MB}m}"

endpoint_ready() {
    curl -fsS "${ES_ENDPOINT}/" >/dev/null 2>&1
}

port_in_use() {
    if command -v lsof >/dev/null 2>&1; then
        lsof -nP -iTCP:"${ES_PORT}" -sTCP:LISTEN >/dev/null 2>&1
        return $?
    fi
    if command -v ss >/dev/null 2>&1; then
        ss -ltn | grep -q ":${ES_PORT} "
        return $?
    fi
    return 1
}

mkdir -p "${ES_STORAGE_PATH}" "${ES_LOG_PATH}" "${ES_CONF_DIR}"

if endpoint_ready; then
    echo "[elastic] deploy reuse existing runtime"
    exit 0
fi

if [ ! -x "${ES_BIN}" ]; then
    ES_VERSION="${ES_VERSION}" bash "${SCRIPT_DIR}/install.sh"
fi

if [ ! -x "${ES_BIN}" ]; then
    echo "Elasticsearch binary not executable: ${ES_BIN}" >&2
    exit 1
fi

if port_in_use; then
    echo "Port ${ES_PORT} is already in use and ${ES_ENDPOINT} is not responding" >&2
    exit 1
fi

ES_HOME="$(cd "$(dirname "${ES_BIN}")/.." && pwd)"

for conf_file in "${ES_HOME}/config/"*; do
    if [ -f "${conf_file}" ]; then
        cp -f "${conf_file}" "${ES_CONF_DIR}/"
    fi
done

cat > "${ES_CONF_DIR}/elasticsearch.yml" <<EOF
cluster.name: agentlogsbench-elastic-bench
node.name: agentlogsbench-elastic-bench-node
path.data: ${ES_STORAGE_PATH}
path.logs: ${ES_LOG_PATH}
network.host: ${ES_HOST}
http.port: ${ES_PORT}
discovery.type: single-node
xpack.security.enabled: false
EOF

if [ "$(id -u)" -eq 0 ]; then
    if ! id "${ES_OS_USER}" >/dev/null 2>&1; then
        useradd -m -r -s /bin/bash "${ES_OS_USER}"
    fi
    chown -R "${ES_OS_USER}:${ES_OS_USER}" "${RUNTIME_DIR}"
    chmod -R a+rX "${ES_HOME}" || true

    temp_script="$(mktemp /tmp/elastic-deploy-XXXX.sh)"
    cat > "${temp_script}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export ES_PATH_CONF="${ES_CONF_DIR}"
export ES_JAVA_OPTS="${ES_JAVA_OPTS}"
"${ES_BIN}" -d -p "${ES_PID_FILE}"
EOF
    chmod 700 "${temp_script}"
    chown "${ES_OS_USER}:${ES_OS_USER}" "${temp_script}"
    su -s /bin/bash "${ES_OS_USER}" -c "${temp_script}"
    rm -f "${temp_script}"
else
    ES_PATH_CONF="${ES_CONF_DIR}" ES_JAVA_OPTS="${ES_JAVA_OPTS}" "${ES_BIN}" -d -p "${ES_PID_FILE}"
fi

for _ in $(seq 1 90); do
    if endpoint_ready; then
        echo "[elastic] deploy done"
        exit 0
    fi
    sleep 1
done

echo "Elasticsearch did not become ready at ${ES_ENDPOINT}" >&2
exit 1
