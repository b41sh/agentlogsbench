DuckDB benchmark lane for `agentlogsbench`.

This lane uses DuckDB `VARIANT` for the semi-structured `payload` column, is designed to fold temporary metric files into the final JSON, and keeps only the final `*.json` plus `_query_results/` under `duckdb/results/`.
