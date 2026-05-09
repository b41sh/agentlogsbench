#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${RUNTIME_DIR:-${SCRIPT_DIR}/runtime}"

OS_ENDPOINT="${OS_ENDPOINT:-http://127.0.0.1:9200}"
OS_HOST="${OS_HOST:-127.0.0.1}"
OS_PORT="${OS_PORT:-9200}"
OS_VERSION="${OS_VERSION:-3.6.0}"
OS_BIN="${OS_BIN:-${SCRIPT_DIR}/.local/opensearch-${OS_VERSION}/bin/opensearch}"
OS_PID_FILE="${OS_PID_FILE:-${RUNTIME_DIR}/opensearch.pid}"
OS_CONF_DIR="${OS_CONF_DIR:-${RUNTIME_DIR}/conf}"
OS_STORAGE_PATH="${OS_STORAGE_PATH:-${RUNTIME_DIR}/data}"
OS_LOG_PATH="${OS_LOG_PATH:-${RUNTIME_DIR}/logs}"
OS_OS_USER="${OS_OS_USER:-agentlogsbenchos}"

default_os_heap_mb() {
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

OS_HEAP_MB="${OS_HEAP_MB:-$(default_os_heap_mb)}"
OS_JAVA_OPTS="${OS_JAVA_OPTS:--Xms${OS_HEAP_MB}m -Xmx${OS_HEAP_MB}m}"

endpoint_ready() {
    curl -fsS "${OS_ENDPOINT}/" >/dev/null 2>&1
}

port_in_use() {
    if command -v lsof >/dev/null 2>&1; then
        lsof -nP -iTCP:"${OS_PORT}" -sTCP:LISTEN >/dev/null 2>&1
        return $?
    fi
    if command -v ss >/dev/null 2>&1; then
        ss -ltn | grep -q ":${OS_PORT} "
        return $?
    fi
    return 1
}

mkdir -p "${OS_STORAGE_PATH}" "${OS_LOG_PATH}" "${OS_CONF_DIR}"

if endpoint_ready; then
    echo "[opensearch] deploy reuse existing runtime"
    exit 0
fi

if [ ! -x "${OS_BIN}" ]; then
    OS_VERSION="${OS_VERSION}" bash "${SCRIPT_DIR}/install.sh"
fi

if [ ! -x "${OS_BIN}" ]; then
    echo "OpenSearch binary not executable: ${OS_BIN}" >&2
    exit 1
fi

if port_in_use; then
    echo "Port ${OS_PORT} is already in use and ${OS_ENDPOINT} is not responding" >&2
    exit 1
fi

OS_HOME="$(cd "$(dirname "${OS_BIN}")/.." && pwd)"
OS_JAVA_HOME="${OS_HOME}/jdk"
if [ ! -f "${OS_JAVA_HOME}/lib/server/libjvm.so" ]; then
    echo "Bundled OpenSearch JDK is incomplete: ${OS_JAVA_HOME}/lib/server/libjvm.so is missing" >&2
    exit 1
fi

for conf_file in "${OS_HOME}/config/"*; do
    if [ -f "${conf_file}" ]; then
        cp -f "${conf_file}" "${OS_CONF_DIR}/"
    fi
done

cat > "${OS_CONF_DIR}/opensearch.yml" <<EOF
cluster.name: agentlogsbench-opensearch-bench
node.name: agentlogsbench-opensearch-bench-node
path.data: ${OS_STORAGE_PATH}
path.logs: ${OS_LOG_PATH}
network.host: ${OS_HOST}
http.port: ${OS_PORT}
discovery.type: single-node
plugins.security.disabled: true
EOF

if [ "$(id -u)" -eq 0 ]; then
    if ! id "${OS_OS_USER}" >/dev/null 2>&1; then
        useradd -m -r -s /bin/bash "${OS_OS_USER}"
    fi
    chown -R "${OS_OS_USER}:${OS_OS_USER}" "${RUNTIME_DIR}"
    chmod -R a+rX "${OS_HOME}" || true

    temp_script="$(mktemp /tmp/opensearch-deploy-XXXX.sh)"
    cat > "${temp_script}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export OPENSEARCH_PATH_CONF="${OS_CONF_DIR}"
export OPENSEARCH_JAVA_OPTS="${OS_JAVA_OPTS}"
export OPENSEARCH_JAVA_HOME="${OS_JAVA_HOME}"
"${OS_BIN}" -d -p "${OS_PID_FILE}"
EOF
    chmod 700 "${temp_script}"
    chown "${OS_OS_USER}:${OS_OS_USER}" "${temp_script}"
    su -s /bin/bash "${OS_OS_USER}" -c "${temp_script}"
    rm -f "${temp_script}"
else
    OPENSEARCH_JAVA_HOME="${OS_JAVA_HOME}" OPENSEARCH_PATH_CONF="${OS_CONF_DIR}" OPENSEARCH_JAVA_OPTS="${OS_JAVA_OPTS}" "${OS_BIN}" -d -p "${OS_PID_FILE}"
fi

for _ in $(seq 1 90); do
    if endpoint_ready; then
        echo "[opensearch] deploy done"
        exit 0
    fi
    sleep 1
done

echo "OpenSearch did not become ready at ${OS_ENDPOINT}" >&2
exit 1
