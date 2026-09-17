"""Delay the experimental patch until the serving process imports SWA cache."""
import importlib
import importlib.abc
import importlib.machinery
import os
import sys


class Loader(importlib.abc.Loader):
    def __init__(self, original):
        self.original = original

    def create_module(self, spec):
        create = getattr(self.original, "create_module", None)
        return create(spec) if create else None

    def exec_module(self, module):
        self.original.exec_module(module)
        importlib.import_module("serving_patch")


class Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != "sglang.srt.mem_cache.swa_radix_cache":
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec and spec.loader:
            spec.loader = Loader(spec.loader)
        return spec


if os.environ.get("EP_MODE"):
    sys.meta_path.insert(0, Finder())

