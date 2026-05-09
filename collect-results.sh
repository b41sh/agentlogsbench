#!/usr/bin/env bash
set -euo pipefail

# ClickBench-style export helper for the local sink table.
# Assumes sink.results stores one JSON result document per engine/machine/dataset_size.

clickhouse-client --query "
SELECT format(
\$\$SELECT output
FROM sink.results
WHERE engine = '{0}' AND machine = '{1}' AND dataset_size = {2}
ORDER BY time DESC
LIMIT 1
INTO OUTFILE '{0}/results/{3}_agentlog_{4}.json'
TRUNCATE
FORMAT Raw
SETTINGS into_outfile_create_parent_directories = 1;\$\$,
engine,
machine,
dataset_size,
replaceRegexpAll(machine, '[^0-9A-Za-z._-]+', '_'),
multiIf(
    dataset_size = 1000000, '1m',
    dataset_size = 10000000, '10m',
    dataset_size = 100000000, '100m',
    toString(dataset_size)
)
)
FROM sink.results
WHERE time >= today() - INTERVAL 1 WEEK
LIMIT 1 BY engine, machine, dataset_size
FORMAT Raw
" | clickhouse-client
