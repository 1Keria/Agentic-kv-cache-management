"""Load native-field dump hooks after SGLang cache/scheduler modules import."""
from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import os
import sys

_WATCH = (
    "sglang.srt.mem_cache.radix_cache",
    "sglang.srt.mem_cache.swa_radix_cache",
    "sglang.srt.mem_cache.hiradix_cache",
    "sglang.srt.mem_cache.common",
    "sglang.srt.managers.scheduler",
    "sglang.srt.managers.tokenizer_manager",
    "sglang.srt.observability.req_time_stats",
)


class _Loader(importlib.abc.Loader):
    def __init__(self, original):
        self.original = original

    def create_module(self, spec):
        create = getattr(self.original, "create_module", None)
        return create(spec) if create else None

    def exec_module(self, module):
        self.original.exec_module(module)
        if os.environ.get("SESSION_RETURN_DUMP_DIR"):
            importlib.import_module("native_dump").install()
        if os.environ.get("SESSION_RETURN_TAU_CKPT"):
            importlib.import_module("tau_evict").install()


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname not in _WATCH:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec and spec.loader:
            spec.loader = _Loader(spec.loader)
        return spec


if os.environ.get("SESSION_RETURN_DUMP_DIR") or os.environ.get(
    "SESSION_RETURN_TAU_CKPT"
):
    sys.meta_path.insert(0, _Finder())
