from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


def load_manifest(manifest_path: Path) -> Dict[str, Any]:
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def manifest_observation_paths(manifest_path: Path, manifest: Dict[str, Any]) -> List[Path]:
    base_dir = manifest_path.parent
    if isinstance(manifest.get("observation_file"), str):
        return [base_dir / manifest["observation_file"]]
    if isinstance(manifest.get("observation_files"), list):
        paths: List[Path] = []
        for item in manifest["observation_files"]:
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                paths.append(base_dir / item["path"])
        return paths
    if isinstance(manifest.get("observation_glob"), str):
        return sorted(base_dir.glob(manifest["observation_glob"]))
    raise KeyError(f"{manifest_path} missing observation_file/observation_files/observation_glob")


def load_context_from_paths(observation_paths: Iterable[Path], replay_trace_id: str) -> Dict[str, str]:
    replay_tenant = None
    replay_app = None
    replay_release_ring = ""
    replay_customer_tier = ""
    replay_traffic_cluster = ""
    replay_request_key = ""
    replay_workflow_variant = ""
    min_biz_date = None
    max_biz_date = None

    for path in observation_paths:
        with _open_text(path) as handle:
            for line in handle:
                row = json.loads(line)
                biz_date = row["biz_date"]
                min_biz_date = biz_date if min_biz_date is None else min(min_biz_date, biz_date)
                max_biz_date = biz_date if max_biz_date is None else max(max_biz_date, biz_date)
                if row.get("trace_id") == replay_trace_id:
                    replay_tenant = row["tenant"]
                    replay_app = row["app"]
                    payload = row.get("payload")
                    attr = payload.get("attr", {}) if isinstance(payload, dict) else {}
                    if isinstance(attr, dict):
                        replay_release_ring = str(attr.get("release_ring") or replay_release_ring)
                        replay_customer_tier = str(attr.get("customer_tier") or replay_customer_tier)
                        replay_traffic_cluster = str(attr.get("traffic_cluster") or replay_traffic_cluster)
                        replay_request_key = str(attr.get("request_key") or replay_request_key)
                        replay_workflow_variant = str(attr.get("workflow_variant") or replay_workflow_variant)

    if replay_tenant is None or replay_app is None or min_biz_date is None or max_biz_date is None:
        raise RuntimeError(f"Could not resolve replay trace context for {replay_trace_id}")

    return {
        "tenant": replay_tenant,
        "app": replay_app,
        "trace_id": replay_trace_id,
        "release_ring": replay_release_ring,
        "customer_tier": replay_customer_tier,
        "traffic_cluster": replay_traffic_cluster,
        "request_key": replay_request_key,
        "workflow_variant": replay_workflow_variant,
        "start_date": min_biz_date,
        "end_date": max_biz_date,
    }
