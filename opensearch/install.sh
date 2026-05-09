#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_DIR="${SCRIPT_DIR}/.local"
OS_VERSION="${OS_VERSION:-3.6.0}"
ARCH="${ARCH:-linux-x64}"
PKG_NAME="opensearch-${OS_VERSION}-${ARCH}"
TAR_NAME="${PKG_NAME}.tar.gz"
URL="https://artifacts.opensearch.org/releases/bundle/opensearch/${OS_VERSION}/${TAR_NAME}"
TARGET_HOME="${LOCAL_DIR}/opensearch-${OS_VERSION}"
TMP_TAR="${LOCAL_DIR}/${TAR_NAME}.part"

if [ -x "${TARGET_HOME}/bin/opensearch" ]; then
    echo "[opensearch] install done"
    exit 0
fi

mkdir -p "${LOCAL_DIR}"

if command -v wget >/dev/null 2>&1; then
    HTTPS_PROXY= HTTP_PROXY= https_proxy= http_proxy= ALL_PROXY= all_proxy= \
        wget -c --tries=10 --waitretry=2 --no-proxy -O "${TMP_TAR}" "${URL}"
else
    HTTPS_PROXY= HTTP_PROXY= https_proxy= http_proxy= ALL_PROXY= all_proxy= \
        curl -fL -C - --retry 5 --retry-delay 2 "${URL}" -o "${TMP_TAR}"
fi
tar -xzf "${TMP_TAR}" -C "${LOCAL_DIR}"

if [ -d "${LOCAL_DIR}/${PKG_NAME}" ] && [ "${LOCAL_DIR}/${PKG_NAME}" != "${TARGET_HOME}" ]; then
    rm -rf "${TARGET_HOME}"
    mv "${LOCAL_DIR}/${PKG_NAME}" "${TARGET_HOME}"
fi

echo "[opensearch] install done"
