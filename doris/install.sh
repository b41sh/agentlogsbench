#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_DIR="${SCRIPT_DIR}/.local"

DORIS_VERSION="${DORIS_VERSION:-4.1.0-rc01}"
DORIS_FULL_NAME="${DORIS_FULL_NAME:-apache-doris-4.1.0-rc01-bin-x64}"
DORIS_HOME="${DORIS_HOME:-${LOCAL_DIR}/${DORIS_FULL_NAME}}"
DORIS_URL="${DORIS_URL:-https://apache-doris-releases.oss-accelerate.aliyuncs.com/apache-doris-4.1.0-rc01-bin-x64.tar.gz}"

ensure_mysql_client() {
    if command -v mysql >/dev/null 2>&1; then
        return 0
    fi

    local sudo_cmd=()
    if [ "$(id -u)" -ne 0 ]; then
        if ! command -v sudo >/dev/null 2>&1 || ! sudo -n true >/dev/null 2>&1; then
            echo "mysql client is required for Doris deploy/import/query and sudo without password is unavailable." >&2
            return 1
        fi
        sudo_cmd=(sudo -n)
    fi

    if [ ! -f /etc/debian_version ]; then
        echo "Automatic mysql client installation is only implemented for Debian/Ubuntu hosts." >&2
        return 1
    fi

    "${sudo_cmd[@]}" apt-get update
    DEBIAN_FRONTEND=noninteractive "${sudo_cmd[@]}" apt-get install -y default-mysql-client
}

ensure_java_runtime() {
    if command -v java >/dev/null 2>&1 && java -version 2>&1 | grep -q '"17\.'; then
        return 0
    fi

    local sudo_cmd=()
    if [ "$(id -u)" -ne 0 ]; then
        if ! command -v sudo >/dev/null 2>&1 || ! sudo -n true >/dev/null 2>&1; then
            echo "Java runtime is required for Doris and sudo without password is unavailable." >&2
            return 1
        fi
        sudo_cmd=(sudo -n)
    fi

    if [ ! -f /etc/debian_version ]; then
        echo "Automatic Java installation is only implemented for Debian/Ubuntu hosts." >&2
        return 1
    fi

    "${sudo_cmd[@]}" apt-get update
    DEBIAN_FRONTEND=noninteractive "${sudo_cmd[@]}" apt-get install -y openjdk-17-jre-headless
}

ensure_mysql_client
ensure_java_runtime

if [ -x "${DORIS_HOME}/fe/bin/start_fe.sh" ] && [ -x "${DORIS_HOME}/be/bin/start_be.sh" ]; then
    echo "[doris] install done"
    exit 0
fi

mkdir -p "${LOCAL_DIR}"
tmp_tar="${LOCAL_DIR}/${DORIS_FULL_NAME}.tar.gz.tmp"
tmp_dir="${LOCAL_DIR}/${DORIS_FULL_NAME}.tmp"

curl -fsSL "${DORIS_URL}" -o "${tmp_tar}"
rm -rf "${tmp_dir}"
mkdir -p "${tmp_dir}"
tar -xzf "${tmp_tar}" -C "${tmp_dir}"
rm -f "${tmp_tar}"

extracted_root="$(find "${tmp_dir}" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
if [ -z "${extracted_root}" ]; then
    echo "Unable to determine extracted Doris directory under ${tmp_dir}" >&2
    exit 1
fi

rm -rf "${DORIS_HOME}"
mv "${extracted_root}" "${DORIS_HOME}"
rm -rf "${tmp_dir}"

echo "[doris] install done"
