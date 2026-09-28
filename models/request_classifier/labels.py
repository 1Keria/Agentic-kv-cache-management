"""Offline label policy for the mixed request-classification corpus."""

from __future__ import annotations

from typing import Any, Mapping


# These GLM source rows are ordinary user tasks despite living in the GLM
# online trace.  Their prompts contain no tool protocol and were manually
# reviewed from the source conversations.
GLM_ORDINARY_SOURCE_LINES = frozenset({1355, 1520, 1696, 1749, 1750, 1848})


def is_agent_like_row(row: Mapping[str, Any]) -> bool:
    traffic_class = str(row.get("traffic_class") or "")
    if traffic_class in {"agent", "openhands"}:
        return True
    if traffic_class != "glm":
        return False
    source = row.get("source") or {}
    try:
        source_line = int(source.get("line_no"))
    except (TypeError, ValueError):
        source_line = None
    return source_line not in GLM_ORDINARY_SOURCE_LINES


def label_name(row: Mapping[str, Any]) -> str:
    return "agent_like" if is_agent_like_row(row) else "request"
