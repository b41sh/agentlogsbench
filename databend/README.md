# Databend Benchmark Lane

This lane uses the Databend Python driver from `bendsql/bindings/python/`.
The benchmark expects an externally managed Databend service by default.
This lane is designed to fold temporary metric files into the final JSON and
keeps only the final `*.json` plus `_query_results/` under `databend/results/`.

## Runtime

Set `DATABEND_DSN` before running Databend scripts:

```bash
export DATABEND_DSN="databend://root:@127.0.0.1:8000/?sslmode=disable"
```

`start.sh` does not launch Databend. It verifies that `databend_driver` can be
imported, opens `DATABEND_DSN`, runs `SELECT 1`, and reports the server version.

By default the script uses the installed `databend-driver` package. It prepends
the in-repository Python package path only when the native extension exists
there:

```bash
bendsql/bindings/python/package
```

Override that path when using a separately built driver:

```bash
export DATABEND_DRIVER_PYTHONPATH=/path/to/databend_driver/package
```

`stop.sh` does not stop the external Databend service. It only removes empty
runtime subdirectories.

## Indexes

`create.sql` declares the primary FUSE cluster key and a Databend inverted index
over `input` and `output`:

```sql
INVERTED INDEX idx_agent_observations_text (input, output)
```

Text-heavy queries use Databend `MATCH()` predicates and `SCORE()` ordering
against that index instead of substring scans. This covers the incident and
retrieval queries `Q05`, `Q08`, `Q11`, `Q13`, `Q14`, `Q15`, and `Q19`.

## Storage metrics

`collect_stats.py` reads row count and storage values from `system.tables`.
Databend reports both a total `index_size` and index-type breakdown fields such
as `inverted_index_size`; the lane records the larger of the total index value
and the summed breakdown so index bytes are not counted twice. The final
JSONBench output embeds `data_size`, `index_size`, and `total_size` through
`artifact_manifest`.

## Contract verification

After loading the bundled small dataset into Databend, run the observation-first
contract runner with the same DSN:

```bash
export DATABEND_DSN="databend://root:@127.0.0.1:8000/?sslmode=disable"
python3 databend/import.py \
  --database agentlogsbench_contract \
  --table agent_observations \
  --data-glob common/generated/small/agent_observations_s.ndjson
DATABEND_DB=agentlogsbench_contract \
  AIBENCH_SKIP_CONTRACT_VERIFICATION=1 \
  RESULT_DIR=/tmp/agentlogsbench-databend-contract \
  bash databend/query.sh
python3 common/validate_run_artifacts.py \
  --results-dir /tmp/agentlogsbench-databend-contract
```

`AIBENCH_SKIP_CONTRACT_VERIFICATION=1` keeps the run in `benchmark_only` mode
until Databend-specific fixture fingerprints are recorded in the shared query
contracts. The validator still checks the runnable result contract, required
fields, query IDs, and latency run shape.
