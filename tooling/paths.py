from __future__ import annotations

from pathlib import Path


def benchmark_root(start: Path | None = None) -> Path:
    here = (start or Path(__file__).resolve()).resolve()
    for parent in [here] + list(here.parents):
        if parent.name == "common" and (parent / "config" / "edition.json").exists():
            return parent.parent
        if (parent / "common" / "config" / "edition.json").exists():
            return parent
        if parent.name != "common" and (parent / "config" / "edition.json").exists():
            return parent
    raise FileNotFoundError("Could not locate agentlogsbench benchmark root")


def common_dir(root: Path) -> Path:
    return root / "common"


def config_dir(root: Path) -> Path:
    candidate = common_dir(root) / "config"
    return candidate if candidate.exists() else root / "config"


def adapters_dir(root: Path) -> Path:
    candidate = common_dir(root) / "adapters"
    return candidate if candidate.exists() else root / "adapters"


def queries_dir(root: Path) -> Path:
    candidate = common_dir(root) / "queries"
    return candidate if candidate.exists() else root / "queries"


def seed_dir(root: Path) -> Path:
    candidate = common_dir(root) / "seeds"
    return candidate if candidate.exists() else root / "seeds"


def contracts_dir(root: Path) -> Path:
    candidate = common_dir(root) / "contracts"
    return candidate if candidate.exists() else root / "tests" / "fixtures"


def bundled_small_data_dir(root: Path) -> Path:
    candidate = common_dir(root) / "generated" / "small"
    return candidate if candidate.exists() else root / "generated" / "small"


def edition_path(root: Path) -> Path:
    return config_dir(root) / "edition.json"


def data_generation_path(root: Path) -> Path:
    return config_dir(root) / "data-generation.json"


def query_suite_path(root: Path) -> Path:
    return queries_dir(root) / "query-suite.json"


def canonical_queries_path(root: Path) -> Path:
    return queries_dir(root) / "queries.sql"


def query_contracts_path(root: Path) -> Path:
    candidate = contracts_dir(root) / "query-contracts.json"
    if candidate.exists():
        return candidate
    return root / "tests" / "fixtures" / "query-contracts.json"


def adapter_manifest_path(root: Path, engine: str) -> Path:
    return adapters_dir(root) / engine / "manifest.json"


def adapter_query_map_path(root: Path, engine: str) -> Path:
    return adapters_dir(root) / engine / "query-map.json"
