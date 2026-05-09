#!/usr/bin/env bash

benchmark_timestamp() {
    date '+%F %T'
}

benchmark_log() {
    local scope="$1"
    shift
    printf '[%s] [%s] %s\n' "$(benchmark_timestamp)" "${scope}" "$*" >&2
}

dataset_file_count() {
    case "$1" in
        1m) echo 1 ;;
        10m) echo 10 ;;
        100m) echo 100 ;;
        *)
            echo "Unsupported dataset size: $1" >&2
            return 1
            ;;
    esac
}

dataset_row_count() {
    case "$1" in
        1m) echo 1000000 ;;
        10m) echo 10000000 ;;
        100m) echo 100000000 ;;
        *)
            echo "Unsupported dataset size: $1" >&2
            return 1
            ;;
    esac
}

prompt_for_dataset_size() {
    echo "Select the dataset size:" >&2
    echo "1) 1m (default)" >&2
    echo "2) 10m" >&2
    echo "3) 100m" >&2
    printf "Enter the number corresponding to your choice: " >&2
    read -r CHOICE

    case "${CHOICE:-1}" in
        2) echo "10m" ;;
        3) echo "100m" ;;
        *) echo "1m" ;;
    esac
}

resolve_dataset_size() {
    local size="${1:-}"
    if [ -z "${size}" ]; then
        prompt_for_dataset_size
        return 0
    fi
    case "${size}" in
        1m|10m|100m)
            echo "${size}"
            return 0
            ;;
        *)
            echo "Unsupported dataset size: ${size}" >&2
            return 1
            ;;
    esac
}

default_download_dir() {
    local root_dir="$1"
    echo "${root_dir}/common/downloads"
}

dataset_download_files() {
    local data_dir="$1"
    local size="$2"
    local file_count
    local index
    local file_name
    local files=()

    file_count="$(dataset_file_count "${size}")"
    for index in $(seq 1 "${file_count}"); do
        printf -v file_name "agent_observations_%04d.ndjson.gz" "${index}"
        files+=("${data_dir}/${file_name}")
    done
    printf '%s\n' "${files[*]}"
}

result_base_name() {
    local output_prefix="$1"
    local size="$2"
    echo "${output_prefix}_agentlog_${size}"
}

default_query_context_file() {
    local root_dir="$1"
    local size="$2"
    echo "${root_dir}/common/context/query_context_${size}.json"
}

aws_instance_type() {
    if [ -n "${BENCHMARK_INSTANCE_TYPE:-}" ]; then
        echo "${BENCHMARK_INSTANCE_TYPE}"
        return 0
    fi

    local token
    token="$(curl -fsS -m 1 -X PUT "http://169.254.169.254/latest/api/token" \
        -H "X-aws-ec2-metadata-token-ttl-seconds: 60" 2>/dev/null || true)"
    if [ -z "${token}" ]; then
        return 1
    fi

    curl -fsS -m 1 -H "X-aws-ec2-metadata-token: ${token}" \
        "http://169.254.169.254/latest/meta-data/instance-type" 2>/dev/null || true
}

default_output_prefix() {
    if [ -n "${OUTPUT_PREFIX:-}" ]; then
        echo "${OUTPUT_PREFIX}"
        return 0
    fi

    local instance_type
    instance_type="$(aws_instance_type || true)"
    if [ -n "${instance_type}" ]; then
        echo "${instance_type}"
        return 0
    fi

    hostname
}

current_os_label() {
    if [ -n "${BENCHMARK_OS:-}" ]; then
        echo "${BENCHMARK_OS}"
        return 0
    fi

    if [ -r /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        if [ -n "${PRETTY_NAME:-}" ]; then
            echo "${PRETTY_NAME}"
            return 0
        fi
    fi

    uname -sr
}

current_machine_label() {
    if [ -n "${BENCHMARK_MACHINE:-}" ]; then
        echo "${BENCHMARK_MACHINE}"
        return 0
    fi

    local instance_type
    local disk_size
    instance_type="$(aws_instance_type || true)"
    disk_size="$(df --output=size -BG / 2>/dev/null | tail -n 1 | tr -dc '0-9')"

    if [ -n "${instance_type}" ] && [ -n "${disk_size}" ]; then
        echo "${instance_type}, ${disk_size}gib root"
        return 0
    fi

    if [ -n "${instance_type}" ]; then
        echo "${instance_type}"
        return 0
    fi

    hostname
}

current_run_date() {
    if [ -n "${BENCHMARK_DATE:-}" ]; then
        echo "${BENCHMARK_DATE}"
        return 0
    fi
    date +%F
}

clear_os_cache() {
    sync
    if [ -w /proc/sys/vm/drop_caches ]; then
        echo 3 > /proc/sys/vm/drop_caches
        return 0
    fi
    if command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
        sudo -n sh -c 'echo 3 > /proc/sys/vm/drop_caches'
        return 0
    fi
    echo "[benchmark] Skipping OS cache drop: root or passwordless sudo is not available" >&2
}
