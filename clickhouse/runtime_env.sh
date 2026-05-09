#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

detect_clickhouse_arch() {
    case "$(uname -m)" in
        x86_64|amd64)
            printf 'amd64\n'
            ;;
        aarch64|arm64)
            printf 'arm64\n'
            ;;
        *)
            printf 'amd64\n'
            ;;
    esac
}

CH_VERSION="${CH_VERSION:-26.2.13.2}"
CH_RELEASE_CHANNEL="${CH_RELEASE_CHANNEL:-stable}"
CH_ARCH="${CH_ARCH:-$(detect_clickhouse_arch)}"
CH_LOCAL_DIR="${CH_LOCAL_DIR:-${SCRIPT_DIR}/.local}"
CH_PACKAGE_NAME="${CH_PACKAGE_NAME:-clickhouse-common-static-${CH_VERSION}-${CH_ARCH}}"
CH_PACKAGE_URL="${CH_PACKAGE_URL:-https://github.com/ClickHouse/ClickHouse/releases/download/v${CH_VERSION}-${CH_RELEASE_CHANNEL}/${CH_PACKAGE_NAME}.tgz}"
CH_HOME_DEFAULT="${CH_HOME_DEFAULT:-${CH_LOCAL_DIR}/${CH_PACKAGE_NAME}}"

resolve_clickhouse_bin() {
    if [ -n "${CH_BIN:-}" ] && [ -x "${CH_BIN}" ]; then
        printf '%s\n' "${CH_BIN}"
        return 0
    fi

    if [ -x "${CH_HOME_DEFAULT}/usr/bin/clickhouse" ]; then
        printf '%s\n' "${CH_HOME_DEFAULT}/usr/bin/clickhouse"
        return 0
    fi

    if command -v clickhouse >/dev/null 2>&1; then
        command -v clickhouse
        return 0
    fi

    return 1
}
