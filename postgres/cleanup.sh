#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/runtime_env.sh"

RUNTIME_DIR="${RUNTIME_DIR:-${SCRIPT_DIR}/runtime}"
RESULT_DIR="${RESULT_DIR:-${SCRIPT_DIR}/results}"
PGDATA="${PGDATA:-${RUNTIME_DIR}/pgdata}"
PG_OS_USER="${PG_OS_USER:-agentlogsbenchpg}"
if [ -z "${PG_BIN_DIR:-}" ]; then
    PG_BIN_DIR="$(resolve_pg_bin_dir || true)"
fi
PG_CTL="${PG_CTL:-${PG_BIN_DIR}/pg_ctl}"

stop_cluster() {
    if [ -x "${PG_CTL}" ] && [ -d "${PGDATA}" ]; then
        "${PG_CTL}" -D "${PGDATA}" -m fast stop >/dev/null 2>&1 || true
    fi
}

if [ "$(id -u)" -eq 0 ] && id "${PG_OS_USER}" >/dev/null 2>&1; then
    temp_script="$(mktemp /tmp/postgres-cleanup-XXXX.sh)"
    cat > "${temp_script}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
PG_CTL="${PG_CTL}"
PGDATA="${PGDATA}"
if [ -x "\${PG_CTL}" ] && [ -d "\${PGDATA}" ]; then
    "\${PG_CTL}" -D "\${PGDATA}" -m fast stop >/dev/null 2>&1 || true
fi
EOF
    chmod 700 "${temp_script}"
    chown "${PG_OS_USER}:${PG_OS_USER}" "${temp_script}"
    su -s /bin/bash "${PG_OS_USER}" -c "${temp_script}" || true
    rm -f "${temp_script}"
else
    stop_cluster
fi

rm -rf "${RUNTIME_DIR}"
rm -rf "${SCRIPT_DIR}/result"
mkdir -p "${RESULT_DIR}"
echo "[postgres] cleanup done"
