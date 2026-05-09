#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

resolve_pg_bin_dir() {
    if [ -n "${PG_BIN_DIR:-}" ] && [ -x "${PG_BIN_DIR}/initdb" ]; then
        printf '%s\n' "${PG_BIN_DIR}"
        return 0
    fi

    if [ -n "${PG_HOME:-}" ] && [ -x "${PG_HOME}/bin/initdb" ]; then
        printf '%s\n' "${PG_HOME}/bin"
        return 0
    fi

    if command -v pg_config >/dev/null 2>&1; then
        pg_bindir="$(pg_config --bindir 2>/dev/null || true)"
        if [ -n "${pg_bindir}" ] && [ -x "${pg_bindir}/initdb" ]; then
            printf '%s\n' "${pg_bindir}"
            return 0
        fi
    fi

    for candidate in /usr/lib/postgresql/*/bin; do
        if [ -x "${candidate}/initdb" ]; then
            printf '%s\n' "${candidate}"
            return 0
        fi
    done

    if command -v initdb >/dev/null 2>&1; then
        dirname "$(command -v initdb)"
        return 0
    fi

    return 1
}

resolve_pg_client_dir() {
    if [ -n "${PG_CLIENT_DIR:-}" ] && [ -d "${PG_CLIENT_DIR}" ]; then
        printf '%s\n' "${PG_CLIENT_DIR}"
        return 0
    fi

    if [ -d "${SCRIPT_DIR}/.local/pg-client" ]; then
        printf '%s\n' "${SCRIPT_DIR}/.local/pg-client"
        return 0
    fi

    return 1
}

tcp_port_in_use() {
    local port="$1"

    if command -v lsof >/dev/null 2>&1; then
        lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
        return $?
    fi
    if command -v ss >/dev/null 2>&1; then
        ss -ltn | grep -q ":${port} "
        return $?
    fi

    return 1
}

resolve_pg_port() {
    local requested_port="${1:-}"
    local base_port="${2:-55432}"
    local candidate

    if [ -n "${requested_port}" ]; then
        printf '%s\n' "${requested_port}"
        return 0
    fi

    for candidate in $(seq "${base_port}" "$((base_port + 32))"); do
        if ! tcp_port_in_use "${candidate}"; then
            printf '%s\n' "${candidate}"
            return 0
        fi
    done

    printf '%s\n' "${base_port}"
    return 0
}

run_python_with_pgclient() {
    local py_path="${PG_CLIENT_DIR:-}"
    if [ -z "${py_path}" ]; then
        py_path="$(resolve_pg_client_dir || true)"
    fi

    if [ -n "${py_path}" ] && [ -d "${py_path}" ]; then
        PYTHONPATH="${py_path}${PYTHONPATH:+:${PYTHONPATH}}" python3 "$@"
        return
    fi

    python3 "$@"
}

python_can_import_psycopg2() {
    run_python_with_pgclient - <<'PY' >/dev/null 2>&1
import psycopg2  # noqa: F401
PY
}

apt_install_postgres_runtime() {
    local sudo_cmd=()
    if [ "$(id -u)" -ne 0 ]; then
        if ! command -v sudo >/dev/null 2>&1 || ! sudo -n true >/dev/null 2>&1; then
            echo "PostgreSQL runtime is missing and sudo without password is unavailable." >&2
            return 1
        fi
        sudo_cmd=(sudo -n)
    fi

    if [ ! -f /etc/debian_version ]; then
        echo "Automatic PostgreSQL installation is only implemented for Debian/Ubuntu hosts." >&2
        return 1
    fi

    "${sudo_cmd[@]}" apt-get update
    DEBIAN_FRONTEND=noninteractive "${sudo_cmd[@]}" apt-get install -y \
        postgresql \
        postgresql-client \
        python3-psycopg2
}
