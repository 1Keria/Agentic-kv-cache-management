"""Online-visible structural features for request traffic classification."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np


FEATURE_NAMES = (
    "has_tools",
    "log_tool_count",
    "log_tool_schema_chars",
    "log_message_count",
    "n_system_messages",
    "n_user_messages",
    "n_assistant_messages",
    "n_tool_messages",
    "n_function_messages",
    "log_tool_call_count",
    "has_tool_role",
    "has_tool_calls",
    "log_content_chars",
    "log_system_chars",
    "log_tool_message_chars",
    "log_max_tokens",
)

FEATURE_GROUPS = {
    "tool_structure": (
        "has_tools",
        "log_tool_count",
        "log_tool_schema_chars",
        "log_tool_call_count",
        "has_tool_role",
        "has_tool_calls",
    ),
    "message_structure": (
        "log_message_count",
        "n_system_messages",
        "n_user_messages",
        "n_assistant_messages",
        "n_tool_messages",
        "n_function_messages",
    ),
    "content_scale": ("log_content_chars", "log_system_chars", "log_tool_message_chars"),
    "budget": ("log_max_tokens",),
}

FEATURE_BUDGETS = {
    1: (
        "n_system_messages",
    ),
    2: (
        "has_tools",
        "n_system_messages",
    ),
    4: (
        "has_tools",
        "log_message_count",
        "n_system_messages",
        "n_tool_messages",
    ),
    8: (
        "has_tools",
        "log_tool_count",
        "log_tool_schema_chars",
        "log_message_count",
        "n_system_messages",
        "n_tool_messages",
        "log_tool_call_count",
        "log_content_chars",
    ),
    12: (
        "has_tools",
        "log_tool_count",
        "log_tool_schema_chars",
        "log_message_count",
        "n_system_messages",
        "n_tool_messages",
        "log_tool_call_count",
        "log_content_chars",
        "has_tool_calls",
        "log_system_chars",
        "log_tool_message_chars",
        "log_max_tokens",
    ),
    16: FEATURE_NAMES,
}

if {name for group in FEATURE_GROUPS.values() for name in group} != set(FEATURE_NAMES):
    raise RuntimeError("FEATURE_GROUPS must cover FEATURE_NAMES exactly")
if not (
    set(FEATURE_BUDGETS[1]) < set(FEATURE_BUDGETS[2])
    and set(FEATURE_BUDGETS[2]) < set(FEATURE_BUDGETS[4])
    and set(FEATURE_BUDGETS[4]) < set(FEATURE_BUDGETS[8])
    and set(FEATURE_BUDGETS[8]) < set(FEATURE_BUDGETS[12])
    and set(FEATURE_BUDGETS[12]) < set(FEATURE_BUDGETS[16])
):
    raise RuntimeError("FEATURE_BUDGETS must be nested")


def _content_chars(value: Any) -> int:
    """Count textual content without using its vocabulary."""
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value)
    if isinstance(value, Mapping):
        return sum(_content_chars(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return sum(_content_chars(item) for item in value)
    return len(str(value))


def _json_chars(value: Any) -> int:
    if not value:
        return 0
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    except (TypeError, ValueError):
        return _content_chars(value)


def _log1p(value: int | float) -> float:
    return math.log1p(max(float(value), 0.0))


def extract_features(prompt_body: Mapping[str, Any] | None, max_tokens: int | float) -> np.ndarray:
    """Return a fixed feature vector without inspecting text vocabulary.

    ``prompt_body`` follows the OpenAI chat format. Session identifiers,
    source metadata, labels, turn indices, and inter-arrival timing are
    intentionally excluded because they are not stable online signals.
    """
    body = prompt_body if isinstance(prompt_body, Mapping) else {}
    messages = body.get("messages") or []
    if not isinstance(messages, Sequence) or isinstance(messages, (str, bytes)):
        messages = []
    tools = body.get("tools") or []
    if not isinstance(tools, Sequence) or isinstance(tools, (str, bytes)):
        tools = []

    role_counts = {"system": 0, "user": 0, "assistant": 0, "tool": 0, "function": 0}
    role_chars = {role: 0 for role in role_counts}
    other_chars = 0
    tool_call_count = 0
    function_call_count = 0
    for message in messages:
        if not isinstance(message, Mapping):
            other_chars += _content_chars(message)
            continue
        role = str(message.get("role") or "")
        chars = _content_chars(message.get("content"))
        if role in role_counts:
            role_counts[role] += 1
            role_chars[role] += chars
        else:
            other_chars += chars
        tool_calls = message.get("tool_calls") or []
        function_call = message.get("function_call")
        if isinstance(tool_calls, Sequence) and not isinstance(tool_calls, (str, bytes)):
            tool_call_count += len(tool_calls)
        elif tool_calls:
            tool_call_count += 1
        if function_call:
            function_call_count += 1

    values = (
        float(bool(tools)),
        _log1p(len(tools)),
        _log1p(_json_chars(tools)),
        _log1p(len(messages)),
        float(role_counts["system"]),
        float(role_counts["user"]),
        float(role_counts["assistant"]),
        float(role_counts["tool"]),
        float(role_counts["function"]),
        _log1p(tool_call_count),
        float(role_counts["tool"] > 0),
        float(tool_call_count > 0 or function_call_count > 0),
        _log1p(sum(role_chars.values()) + other_chars),
        _log1p(role_chars["system"]),
        _log1p(role_chars["tool"]),
        _log1p(max_tokens),
    )
    return np.asarray(values, dtype=np.float32)


def feature_dict(prompt_body: Mapping[str, Any] | None, max_tokens: int | float) -> dict[str, float]:
    return dict(zip(FEATURE_NAMES, extract_features(prompt_body, max_tokens).tolist()))
