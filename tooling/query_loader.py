from __future__ import annotations

from pathlib import Path
from typing import Dict


def load_query_sections(path: Path) -> Dict[str, str]:
    text = path.read_text(encoding="utf-8")
    sections: Dict[str, str] = {}
    current_id: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        if line.startswith("-- Q"):
            if current_id is not None:
                sections[current_id] = "\n".join(current_lines).strip()
            current_id = line.replace("--", "", 1).strip()
            current_lines = []
            continue
        if current_id is not None:
            current_lines.append(line)

    if current_id is not None:
        sections[current_id] = "\n".join(current_lines).strip()

    return sections


def load_query_sql(path: Path, query_id: str) -> str:
    sections = load_query_sections(path)
    if query_id not in sections:
        raise KeyError(f"{path} missing query section {query_id}")
    return sections[query_id]
