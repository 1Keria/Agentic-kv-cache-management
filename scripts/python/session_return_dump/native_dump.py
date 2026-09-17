"""Dump native SGLang fields at request-end / eviction / API finish.

Enabled when SESSION_RETURN_DUMP_DIR is set. Writes JSONL, one object per event.
Does not invent aggregations (n_children, age, TTFT, ...). Replay-clock timestamps
are stored as their native fields; they are not labels.
"""
from __future__ import annotations

import json
import os
import threading
import time
from array import array
from pathlib import Path
from typing import Any, Optional

SCHEMA = "session_return_native_v1"
_SKIP_NODE = {
    "reuse_strength",
    "last_turnover",
    "reuse_count",
    "terminal_count",
    "prefix_depth",
    "reuse_value_density",
}
_SKIP_CUSTOM = {
    "session_id",
    "turn_idx",
    "traffic_class",
    "has_tools",
    "__req__",
}

_lock = threading.Lock()
_installed = False
_fd: Optional[int] = None
_seq = 0
_scheduler = None
_tokenized: dict[str, Any] = {}


def _dump_dir() -> Optional[Path]:
    raw = os.environ.get("SESSION_RETURN_DUMP_DIR")
    if not raw:
        return None
    return Path(raw)


def _open_log() -> Optional[int]:
    global _fd
    if _fd is not None:
        return _fd
    root = _dump_dir()
    if root is None:
        return None
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"native_pid{os.getpid()}.jsonl"
    _fd = os.open(str(path), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    return _fd


def emit(event: str, **payload: Any) -> None:
    fd = _open_log()
    if fd is None:
        return
    global _seq
    with _lock:
        _seq += 1
        row = {
            "schema": SCHEMA,
            "event": event,
            "pid": os.getpid(),
            "seq": _seq,
            "time_unix_s": time.time(),
            "time_monotonic_s": time.monotonic(),
            **payload,
        }
        os.write(
            fd,
            (json.dumps(row, ensure_ascii=False, default=str) + "\n").encode(),
        )


def _as_int_list(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, array):
        return list(value)
    if hasattr(value, "detach") and hasattr(value, "tolist"):
        try:
            return value.detach().cpu().tolist()
        except Exception:
            return None
    if isinstance(value, (list, tuple)):
        if value and isinstance(value[0], (list, tuple)):
            return None
        try:
            return [int(x) for x in value]
        except Exception:
            return list(value)
    return None


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, array):
        return list(value)
    if isinstance(value, (list, tuple)):
        if len(value) > 0 and isinstance(value[0], (list, float)):
            return None
        return [_jsonable(x) for x in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if hasattr(value, "detach") and hasattr(value, "tolist"):
        try:
            if getattr(value, "ndim", 1) > 1:
                return None
            return value.detach().cpu().tolist()
        except Exception:
            return None
    return str(value)


def dump_key(key: Any) -> Any:
    if key is None:
        return None
    return {
        "token_ids": _as_int_list(getattr(key, "token_ids", None)),
        "extra_key": getattr(key, "extra_key", None),
        "is_bigram": bool(getattr(key, "is_bigram", False)),
    }


def dump_node(node: Any) -> Any:
    if node is None:
        return None
    parent = getattr(node, "parent", None)
    children = []
    mapping = getattr(node, "children", None) or {}
    try:
        items = mapping.items()
    except Exception:
        items = []
    for child_key, child in items:
        children.append(
            {
                "id": getattr(child, "id", None),
                "key": dump_key(child_key)
                if hasattr(child_key, "token_ids")
                else _jsonable(child_key),
            }
        )
    row = {
        "id": getattr(node, "id", None),
        "parent_id": None if parent is None else getattr(parent, "id", None),
        "children": children,
        "key": dump_key(getattr(node, "key", None)),
        "value": _as_int_list(getattr(node, "value", None)),
        "last_access_time": getattr(node, "last_access_time", None),
        "hit_count": getattr(node, "hit_count", None),
        "host_value": _as_int_list(getattr(node, "host_value", None)),
        "hash_value": list(node.hash_value)
        if getattr(node, "hash_value", None) is not None
        else None,
        "lock_ref": getattr(node, "lock_ref", None),
        "creation_time": getattr(node, "creation_time", None),
        "host_ref_counter": getattr(node, "host_ref_counter", None),
        "write_through_pending_id": getattr(node, "write_through_pending_id", None),
        "priority": getattr(node, "priority", None),
        "swa_tombstone": getattr(node, "swa_tombstone", None),
        "full_lock_ref": getattr(node, "full_lock_ref", None),
        "swa_lock_ref": getattr(node, "swa_lock_ref", None),
        "prev_id": getattr(getattr(node, "prev", None), "id", None),
        "next_id": getattr(getattr(node, "next", None), "id", None),
        "swa_prev_id": getattr(getattr(node, "swa_prev", None), "id", None),
        "swa_next_id": getattr(getattr(node, "swa_next", None), "id", None),
        "swa_uuid": getattr(node, "swa_uuid", None),
    }
    for name in _SKIP_NODE:
        row.pop(name, None)
    return row


def dump_sampling(params: Any) -> Any:
    if params is None:
        return None
    custom = getattr(params, "custom_params", None)
    if isinstance(custom, dict):
        custom = {
            k: _jsonable(v) for k, v in custom.items() if k not in _SKIP_CUSTOM
        }
    else:
        custom = None
    return {
        "max_new_tokens": getattr(params, "max_new_tokens", None),
        "stop_strs": _jsonable(getattr(params, "stop_strs", None)),
        "stop_token_ids": _jsonable(getattr(params, "stop_token_ids", None)),
        "stop_regex_strs": _jsonable(getattr(params, "stop_regex_strs", None)),
        "temperature": getattr(params, "temperature", None),
        "top_p": getattr(params, "top_p", None),
        "top_k": getattr(params, "top_k", None),
        "min_p": getattr(params, "min_p", None),
        "frequency_penalty": getattr(params, "frequency_penalty", None),
        "presence_penalty": getattr(params, "presence_penalty", None),
        "repetition_penalty": getattr(params, "repetition_penalty", None),
        "min_new_tokens": getattr(params, "min_new_tokens", None),
        "n": getattr(params, "n", None),
        "ignore_eos": getattr(params, "ignore_eos", None),
        "no_stop_trim": getattr(params, "no_stop_trim", None),
        "sampling_seed": getattr(params, "sampling_seed", None),
        "custom_params": custom,
    }


def dump_time_stats(stats: Any) -> Any:
    if stats is None:
        return None
    names = (
        "created_time",
        "tokenize_finish_time",
        "api_server_dispatch_time",
        "api_server_dispatch_finish_time",
        "first_token_time",
        "last_time",
        "finished_time",
        "response_sent_to_client_time",
        "scheduler_recv_time",
        "wait_queue_entry_time",
        "forward_entry_time",
        "prefill_finished_time",
        "completion_time",
        "dpc_dispatch_time",
    )
    return {name: getattr(stats, name, None) for name in names}


def dump_session(session: Any) -> Any:
    if session is None:
        return None
    req_nodes = getattr(session, "req_nodes", None) or {}
    return {
        "session_id": getattr(session, "session_id", None),
        "capacity_of_str_len": getattr(session, "capacity_of_str_len", None),
        "streaming": getattr(session, "streaming", None),
        "timeout": getattr(session, "timeout", None),
        "last_active_time": getattr(session, "last_active_time", None),
        "req_nodes": [str(k) for k in req_nodes.keys()],
        "close_on_finish": getattr(session, "close_on_finish", None),
        "_inflight": getattr(session, "_inflight", None),
    }


def dump_finished_reason(reason: Any) -> Any:
    if reason is None:
        return None
    if hasattr(reason, "to_json"):
        try:
            return reason.to_json()
        except Exception:
            pass
    return {"type": type(reason).__name__, "repr": str(reason)}


def dump_req(req: Any) -> Any:
    mm = getattr(req, "multimodal_inputs", None)
    return {
        "rid": getattr(req, "rid", None),
        "origin_input_ids": _as_int_list(getattr(req, "origin_input_ids", None)),
        "origin_input_ids_unpadded": _as_int_list(
            getattr(req, "origin_input_ids_unpadded", None)
        ),
        "output_ids": _as_int_list(getattr(req, "output_ids", None)),
        "full_untruncated_fill_ids": _as_int_list(
            getattr(req, "full_untruncated_fill_ids", None)
        ),
        "fill_len": getattr(req, "fill_len", None),
        "input_embeds": None
        if getattr(req, "input_embeds", None) is None
        else True,
        "multimodal_inputs": None if mm is None else type(mm).__name__,
        "sampling_params": dump_sampling(getattr(req, "sampling_params", None)),
        "session": dump_session(getattr(req, "session", None)),
        "extra_key": getattr(req, "extra_key", None),
        "lora_id": getattr(req, "lora_id", None),
        "routing_key": getattr(req, "routing_key", None),
        "priority": getattr(req, "priority", None),
        "require_reasoning": getattr(req, "require_reasoning", None),
        "_is_reasoning_over": getattr(req, "_is_reasoning_over", None),
        "reasoning_tokens": getattr(req, "reasoning_tokens", None),
        "finished_reason": dump_finished_reason(getattr(req, "finished_reason", None)),
        "finished_len": getattr(req, "finished_len", None),
        "to_finish": dump_finished_reason(getattr(req, "to_finish", None)),
        "prefix_indices": _as_int_list(getattr(req, "prefix_indices", None)),
        "last_node": dump_node(getattr(req, "last_node", None)),
        "last_host_node": dump_node(getattr(req, "last_host_node", None)),
        "best_match_node": dump_node(getattr(req, "best_match_node", None)),
        "host_hit_length": getattr(req, "host_hit_length", None),
        "swa_host_hit_length": getattr(req, "swa_host_hit_length", None),
        "mamba_host_hit_length": getattr(req, "mamba_host_hit_length", None),
        "num_matched_prefix_tokens": getattr(req, "num_matched_prefix_tokens", None),
        "storage_hit_length": getattr(req, "storage_hit_length", None),
        "cache_protected_len": getattr(req, "cache_protected_len", None),
        "cached_tokens": getattr(req, "cached_tokens", None),
        "cached_tokens_device": getattr(req, "cached_tokens_device", None),
        "cached_tokens_host": getattr(req, "cached_tokens_host", None),
        "cached_tokens_storage": getattr(req, "cached_tokens_storage", None),
        "kv_committed_len": getattr(req, "kv_committed_len", None),
        "kv_allocated_len": getattr(req, "kv_allocated_len", None),
        "swa_evicted_seqlen": getattr(req, "swa_evicted_seqlen", None),
        "extend_input_len": getattr(req, "extend_input_len", None),
        "stream": getattr(req, "stream", None),
        "time_stats": dump_time_stats(getattr(req, "time_stats", None)),
    }


def _call_int(obj: Any, name: str) -> Any:
    fn = getattr(obj, name, None)
    if fn is None:
        return None
    try:
        return int(fn() if callable(fn) else fn)
    except Exception:
        return None


def dump_resource(cache: Any) -> dict[str, Any]:
    alloc = getattr(cache, "token_to_kv_pool_allocator", None)
    row: dict[str, Any] = {
        "cache_type": type(cache).__name__,
        "page_size": getattr(cache, "page_size", None),
        "size": getattr(alloc, "size", None) if alloc is not None else None,
        "available_size": _call_int(alloc, "available_size") if alloc else None,
        "full_available_size": _call_int(alloc, "full_available_size") if alloc else None,
        "swa_available_size": _call_int(alloc, "swa_available_size") if alloc else None,
        "evictable_size": _call_int(cache, "evictable_size"),
        "protected_size": _call_int(cache, "protected_size"),
        "full_evictable_size_": getattr(cache, "full_evictable_size_", None),
        "swa_evictable_size_": getattr(cache, "swa_evictable_size_", None),
        "full_protected_size_": getattr(cache, "full_protected_size_", None),
        "swa_protected_size_": getattr(cache, "swa_protected_size_", None),
        "sliding_window_size": getattr(cache, "sliding_window_size", None)
        or getattr(alloc, "sliding_window_size", None),
        "evictable_size_": getattr(cache, "evictable_size_", None),
        "protected_size_": getattr(cache, "protected_size_", None),
    }
    if isinstance(row.get("evictable_size"), tuple):
        row["evictable_size"] = [int(x) for x in row["evictable_size"]]
    return row


def dump_queues() -> dict[str, Any]:
    sched = _scheduler
    if sched is None:
        return {"waiting_queue": None, "running_batch": None, "cur_batch": None}

    def rids(reqs: Any) -> list[Any]:
        out = []
        for req in reqs or []:
            out.append(getattr(req, "rid", None))
        return out

    waiting = getattr(sched, "waiting_queue", None)
    running = getattr(sched, "running_batch", None)
    current = getattr(sched, "cur_batch", None)
    return {
        "waiting_queue": rids(waiting),
        "running_batch": rids(getattr(running, "reqs", None)),
        "cur_batch": rids(getattr(current, "reqs", None)) if current is not None else None,
    }


def dump_tokenized(recv_req: Any) -> dict[str, Any]:
    session_params = getattr(recv_req, "session_params", None)
    return {
        "rid": getattr(recv_req, "rid", None),
        "input_text": getattr(recv_req, "input_text", None),
        "input_ids": _as_int_list(getattr(recv_req, "input_ids", None)),
        "mm_inputs": None
        if getattr(recv_req, "mm_inputs", None) is None
        else type(recv_req.mm_inputs).__name__,
        "sampling_params": dump_sampling(getattr(recv_req, "sampling_params", None)),
        "session_params": None
        if session_params is None
        else {
            name: _jsonable(getattr(session_params, name, None))
            for name in (
                "id",
                "rid",
                "offset",
                "replace",
                "drop_previous_output",
            )
            if hasattr(session_params, name)
        },
        "extra_key": getattr(recv_req, "extra_key", None),
        "routing_key": getattr(recv_req, "routing_key", None),
        "priority": getattr(recv_req, "priority", None),
        "stream": getattr(recv_req, "stream", None),
        "time_stats": dump_time_stats(getattr(recv_req, "time_stats", None)),
        "lora_id": getattr(recv_req, "lora_id", None),
    }


def _wrap(cls: Any, name: str, wrapper) -> None:
    orig = getattr(cls, name, None)
    if orig is None or getattr(orig, "_sr_patched", False):
        return
    wrapped = wrapper(orig)
    wrapped._sr_patched = True
    setattr(cls, name, wrapped)


def _patch_cache_finished(cls: Any) -> None:
    def wrapper(orig):
        def cache_finished_req(self, req, *args, **kwargs):
            rid = getattr(req, "rid", None)
            req_snapshot = None
            tokenized = None
            try:
                tokenized = (
                    _tokenized.pop(str(rid), None) if rid is not None else None
                )
                req_snapshot = dump_req(req)
            except Exception as exc:  # noqa: BLE001
                emit("dump_error", where="request_end_snapshot", error=str(exc), rid=rid)
            try:
                return orig(self, req, *args, **kwargs)
            finally:
                try:
                    emit(
                        "request_end",
                        rid=rid,
                        is_insert=kwargs.get(
                            "is_insert", args[0] if args else True
                        ),
                        tokenized=tokenized,
                        req=req_snapshot,
                        resource=dump_resource(self),
                        scheduler=dump_queues(),
                    )
                except Exception as exc:  # noqa: BLE001
                    emit("dump_error", where="request_end", error=str(exc), rid=rid)

        return cache_finished_req

    _wrap(cls, "cache_finished_req", wrapper)


def _patch_evict(cls: Any) -> None:
    def wrapper(orig):
        def evict(self, params, *args, **kwargs):
            num_tokens = getattr(params, "num_tokens", None)
            swa_num_tokens = getattr(params, "swa_num_tokens", None)
            try:
                emit(
                    "evict_start",
                    num_tokens=num_tokens,
                    swa_num_tokens=swa_num_tokens,
                    resource=dump_resource(self),
                    scheduler=dump_queues(),
                )
            except Exception:
                pass
            result = orig(self, params, *args, **kwargs)
            try:
                emit(
                    "evict_end",
                    num_tokens=num_tokens,
                    swa_num_tokens=swa_num_tokens,
                    num_tokens_evicted=getattr(result, "num_tokens_evicted", None),
                    swa_num_tokens_evicted=getattr(
                        result, "swa_num_tokens_evicted", None
                    ),
                    resource=dump_resource(self),
                    scheduler=dump_queues(),
                )
            except Exception as exc:  # noqa: BLE001
                emit("dump_error", where="evict_end", error=str(exc))
            return result

        return evict

    _wrap(cls, "evict", wrapper)


def _patch_delete_leaf(cls: Any) -> None:
    def wrapper(orig):
        def _delete_leaf(self, node, *args, **kwargs):
            try:
                payload = dump_node(node)
            except Exception:
                payload = {"id": getattr(node, "id", None)}
            result = orig(self, node, *args, **kwargs)
            try:
                emit("evict_node", node=payload, cache_type=type(self).__name__)
            except Exception:
                pass
            return result

        return _delete_leaf

    _wrap(cls, "_delete_leaf", wrapper)


def _patch_hi_evict_helpers(cls: Any) -> None:
    for name, medium in (
        ("_evict_regular", "device"),
        ("_evict_backuped", "device_to_host"),
    ):
        orig = getattr(cls, name, None)
        if orig is None or getattr(orig, "_sr_patched", False):
            continue

        def wrapper(orig=orig, medium=medium):
            def method(self, node, *args, **kwargs):
                try:
                    payload = dump_node(node)
                except Exception:
                    payload = {"id": getattr(node, "id", None)}
                result = orig(self, node, *args, **kwargs)
                try:
                    emit(
                        "evict_node",
                        medium=medium,
                        node=payload,
                        cache_type=type(self).__name__,
                    )
                except Exception:
                    pass
                return result

            method._sr_patched = True
            return method

        setattr(cls, name, wrapper())

    orig_host = getattr(cls, "evict_host", None)
    if orig_host is not None and not getattr(orig_host, "_sr_patched", False):

        def evict_host(self, num_tokens, *args, **kwargs):
            try:
                emit(
                    "evict_host_start",
                    num_tokens=num_tokens,
                    resource=dump_resource(self),
                )
            except Exception:
                pass
            result = orig_host(self, num_tokens, *args, **kwargs)
            try:
                emit(
                    "evict_host_end",
                    num_tokens=num_tokens,
                    num_tokens_evicted=result,
                    resource=dump_resource(self),
                )
            except Exception:
                pass
            return result

        evict_host._sr_patched = True
        cls.evict_host = evict_host


def _patch_common(mod: Any) -> None:
    orig = getattr(mod, "evict_from_tree_cache", None)
    if orig is None or getattr(orig, "_sr_patched", False):
        return

    def evict_from_tree_cache(tree_cache, num_tokens):
        try:
            emit(
                "evict_trigger",
                num_tokens=int(num_tokens),
                resource=None if tree_cache is None else dump_resource(tree_cache),
            )
        except Exception:
            pass
        return orig(tree_cache, num_tokens)

    evict_from_tree_cache._sr_patched = True
    mod.evict_from_tree_cache = evict_from_tree_cache


def _patch_scheduler(mod: Any) -> None:
    cls = getattr(mod, "Scheduler", None)
    if cls is None:
        return

    def wrap_init(orig):
        def __init__(self, *args, **kwargs):
            global _scheduler
            orig(self, *args, **kwargs)
            _scheduler = self

        return __init__

    _wrap(cls, "__init__", wrap_init)

    def wrap_generate(orig):
        def handle_generate_request(self, recv_req):
            try:
                rid = str(getattr(recv_req, "rid", ""))
                payload = dump_tokenized(recv_req)
                if rid:
                    _tokenized[rid] = payload
                emit("tokenized", **payload)
            except Exception as exc:  # noqa: BLE001
                emit("dump_error", where="tokenized", error=str(exc))
            return orig(self, recv_req)

        return handle_generate_request

    _wrap(cls, "handle_generate_request", wrap_generate)


def _patch_time_stats(mod: Any) -> None:
    cls = getattr(mod, "APIServerReqTimeStats", None)
    if cls is None:
        return

    def wrap(orig):
        def set_response_sent_to_client_time(self, ts=None):
            orig(self, ts)
            try:
                emit(
                    "api_time_stats",
                    rid=getattr(self, "_sr_rid", None),
                    time_stats=dump_time_stats(self),
                )
            except Exception:
                pass

        return set_response_sent_to_client_time

    _wrap(cls, "set_response_sent_to_client_time", wrap)


def _patch_tokenizer(mod: Any) -> None:
    cls = getattr(mod, "TokenizerManager", None)
    if cls is None:
        return

    def wrap_init_state(orig):
        def _init_req_state(self, obj, request=None):
            orig(self, obj, request)
            try:
                rids = obj.rid if isinstance(getattr(obj, "rid", None), list) else [obj.rid]
                for rid in rids:
                    state = self.rid_to_state.get(rid)
                    if state is None:
                        continue
                    state.time_stats._sr_rid = rid
            except Exception:
                pass

        return _init_req_state

    _wrap(cls, "_init_req_state", wrap_init_state)


def install() -> None:
    global _installed
    if _dump_dir() is None:
        return
    import sys

    _patch_targets = [
        ("sglang.srt.mem_cache.radix_cache", "RadixCache", True, False),
        ("sglang.srt.mem_cache.swa_radix_cache", "SWARadixCache", True, False),
        ("sglang.srt.mem_cache.hiradix_cache", "HiRadixCache", True, True),
    ]
    for mod_name, cls_name, evict, hi in _patch_targets:
        mod = sys.modules.get(mod_name)
        if mod is None:
            continue
        cls = getattr(mod, cls_name, None)
        if cls is None:
            continue
        _patch_cache_finished(cls)
        if evict:
            _patch_evict(cls)
        _patch_delete_leaf(cls)
        if hi:
            _patch_hi_evict_helpers(cls)

    common = sys.modules.get("sglang.srt.mem_cache.common")
    if common is not None:
        _patch_common(common)
    sched = sys.modules.get("sglang.srt.managers.scheduler")
    if sched is not None:
        _patch_scheduler(sched)
    ts = sys.modules.get("sglang.srt.observability.req_time_stats")
    if ts is not None:
        _patch_time_stats(ts)
    tok = sys.modules.get("sglang.srt.managers.tokenizer_manager")
    if tok is not None:
        _patch_tokenizer(tok)

    if not _installed:
        _installed = True
        emit(
            "dump_init",
            dump_dir=str(_dump_dir()),
            python=sys.executable,
        )
