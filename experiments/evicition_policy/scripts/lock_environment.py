#!/usr/bin/env python3
"""Fingerprint the isolated official installation, without recording secrets."""

import datetime
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import zipfile

import sglang
import torch

from prepare_data import ROOT, digest_file, save_json


def capture() -> dict:
    package = Path(sglang.__file__).resolve().parent
    if not package.is_relative_to(ROOT / "runtime/venv"):
        raise ValueError("Non-isolated package import")
    wheel = ROOT / "runtime/wheels/sglang-0.5.13.post1-cp312-cp312-manylinux_2_34_x86_64.whl"
    verified = 0
    with zipfile.ZipFile(wheel) as archive:
        for entry in archive.infolist():
            if entry.is_dir() or not entry.filename.startswith("sglang/"):
                continue
            installed = package.parent / entry.filename
            if not installed.is_file() or digest_file(installed) != hashlib.sha256(archive.read(entry)).hexdigest():
                raise ValueError(f"Installed package differs from release wheel: {entry.filename}")
            verified += 1
    model = Path(json.loads((ROOT / "configs/smoke_server.json").read_text())["model_path"])
    names = ["config.json", "generation_config.json", "tokenizer.json", "tokenizer_config.json", "model.safetensors.index.json"]
    files = {name: digest_file(model / name) for name in names if (model / name).is_file()}
    shards = list(model.glob("*.safetensors"))
    source_names = ["srt/mem_cache/evict_policy.py", "srt/mem_cache/registry.py",
                    "srt/mem_cache/unified_radix_cache.py", "srt/mem_cache/unified_cache_components/full_component.py",
                    "srt/mem_cache/unified_cache_components/swa_component.py", "srt/configs/model_config.py",
                    "srt/model_executor/pool_configurator.py", "srt/entrypoints/openai/serving_chat.py",
                    "srt/entrypoints/openai/encoding_dsv4.py", "srt/managers/tokenizer_manager.py"]
    source_hashes = {name: digest_file(package / name) for name in source_names}
    freeze = subprocess.run([sys.executable, "-m", "pip", "freeze", "--all"], capture_output=True, text=True, check=True).stdout
    check = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, text=True, check=True).stdout
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=index,uuid,name,driver_version,memory.total", "--format=csv,noheader"],
                         capture_output=True, text=True, check=True).stdout
    return {"schema": 1, "captured_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "engine": {"version": importlib.metadata.version("sglang"), "origin": str(package),
                       "provenance": "official_release_wheel", "git_commit": None,
                       "wheel": str(wheel.relative_to(ROOT)), "wheel_sha256": digest_file(wheel),
                       "installed_files_verified_against_wheel": verified, "source_hashes": source_hashes},
            "python": sys.version, "python_executable": sys.executable, "platform": platform.platform(),
            "torch": torch.__version__, "torch_cuda": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(), "gpu_inventory_csv": gpu,
            "dependency_freeze": freeze.splitlines(), "pip_check": check.strip(),
            "environment": {name: os.environ.get(name) for name in [
                "SGLANG_ENABLE_UNIFIED_RADIX_TREE", "SGLANG_EXPERIMENTAL_CPP_RADIX_TREE",
                "SGLANG_DEFAULT_THINKING", "SGLANG_DSV4_REASONING_EFFORT", "CUDA_VISIBLE_DEVICES",
                "PYTHONNOUSERSITE", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"]},
            "model": {"path": str(model), "metadata_sha256": files, "weight_shards": len(shards),
                      "weight_bytes": sum(path.stat().st_size for path in shards), "full_weight_hashes_verified": False}}


def main():
    output = ROOT / "configs/environment.lock.json"
    if output.exists():
        raise FileExistsError("Environment lock exists; do not silently overwrite it")
    os.umask(0o077)
    result = capture()
    save_json(output, result)
    print(json.dumps({"lock": str(output), "engine_version": result["engine"]["version"],
                      "wheel_files_verified": result["engine"]["installed_files_verified_against_wheel"]}))


if __name__ == "__main__":
    main()
