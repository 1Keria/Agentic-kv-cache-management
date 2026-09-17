"""Install the cold-frontier patch only after SGLang naturally imports SWA cache."""

import importlib
import importlib.abc
import importlib.machinery
import os
import sys


TARGET = "sglang.srt.mem_cache.swa_radix_cache"


class _AfterLoader(importlib.abc.Loader):
    def __init__(self, original):
        self.original = original

    def create_module(self, spec):
        create = getattr(self.original, "create_module", None)
        return create(spec) if create is not None else None

    def exec_module(self, module):
        self.original.exec_module(module)
        importlib.import_module("cold_frontier_patch_impl")


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != TARGET:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None:
            return spec
        spec.loader = _AfterLoader(spec.loader)
        return spec


if os.environ.get("COLD_FRONTIER_TRACE_DIR"):
    sys.meta_path.insert(0, _Finder())
