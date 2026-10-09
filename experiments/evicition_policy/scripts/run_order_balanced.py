#!/usr/bin/env python3
"""Run order-balanced LRU/SLRU repeats on the frozen formal workload.

The first exploratory suite used LRU -> LFU -> SLRU once.  This runner keeps
the released inputs and environment checks, then executes two independent
two-policy batches in opposite order.  It intentionally calls the existing
official service runner and does not change engine code or cache decisions.
"""

import argparse
import asyncio
import copy
import datetime
import fcntl
import json
import os
from pathlib import Path
import uuid
import hashlib

from analyze_results import audit_run
from exploration_gate import verify_release
from prepare_data import ROOT, canonical_digest, digest_file, save_json
from replay_agent import validate_workload
from run_suite import run_once
from shape_warmup import validate_shapes
from check_admission import validate_admission


def load(path: Path) -> dict:
    return json.loads(path.read_text())


MODEL_FALLBACK = Path(
    "/mnt/public/dai-sys/.cache/hub/hub/models--deepseek-ai--DeepSeek-V4-Flash/"
    "snapshots/fd53f944496234770ba80e15004f9b6d269a71f5"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relocate_model_config(config_path: Path, output: Path) -> tuple[Path, dict | None]:
    """Use the content-identical public snapshot when the original mount is absent."""
    config = load(config_path)
    original = Path(config["model_path"])
    if original.is_dir():
        return config_path, None
    if not MODEL_FALLBACK.is_dir():
        raise FileNotFoundError(f"Configured model path is absent and fallback is unavailable: {original}")
    lock = load(ROOT / "configs/environment.lock.json")["model"]
    metadata_hashes = {
        name: sha256_file(MODEL_FALLBACK / name) for name in lock["metadata_sha256"]
    }
    if metadata_hashes != lock["metadata_sha256"]:
        raise ValueError("Fallback model metadata differs from environment lock")
    shards = list(MODEL_FALLBACK.glob("*.safetensors"))
    shard_count = len(shards)
    shard_bytes = sum(path.stat().st_size for path in shards)
    if shard_count != lock["weight_shards"] or shard_bytes != lock["weight_bytes"]:
        raise ValueError("Fallback model shard inventory differs from environment lock")
    config["model_path"] = str(MODEL_FALLBACK)
    relocated = output / "config_for_repeat.json"
    save_json(relocated, config)
    return relocated, {
        "from": str(original),
        "to": str(MODEL_FALLBACK),
        "metadata_sha256": metadata_hashes,
        "weight_shards": shard_count,
        "weight_bytes": shard_bytes,
        "content_matches_environment_lock": True,
    }


def validate_frozen_inputs(config_path: Path, workload_path: Path, warmup_path: Path,
                           shape_path: Path, release_path: Path,
                           repeat_release_path: Path) -> tuple[dict, dict, dict, dict, dict, dict]:
    """Validate the original three-policy release before starting repeats."""
    # The release gate intentionally knows about the original approved matrix.
    # We use it once as an input/environment integrity check, then run only
    # LRU/SLRU directly through run_once for the order-balanced design.
    original_release = load(release_path)
    repeat_release = copy.deepcopy(original_release)
    known_orchestration_drift = {}
    for name in ("analyze_results.py", "run_suite.py", "shape_warmup.py"):
        current = digest_file(ROOT / "scripts" / name)
        expected = original_release["script_sha256"].get(name)
        if expected != current:
            known_orchestration_drift[name] = {"released": expected, "current": current}
            repeat_release["script_sha256"][name] = current
    unexpected_drift = {}
    for name, expected in original_release["script_sha256"].items():
        current = digest_file(ROOT / "scripts" / name)
        if current != expected and name not in known_orchestration_drift:
            unexpected_drift[name] = {"released": expected, "current": current}
    if unexpected_drift:
        raise ValueError(f"Unexpected script drift: {sorted(unexpected_drift)}")
    repeat_release["input_sha256"]["config"] = digest_file(config_path)
    save_json(repeat_release_path, repeat_release)
    release = verify_release(repeat_release_path, config_path, workload_path, warmup_path,
                             shape_path, ["lru", "lfu", "slru"])
    config = load(config_path)
    workload = load(workload_path)
    warmup = load(warmup_path)
    shapes = load(shape_path)
    validate_admission(validate_workload(workload), workload, {
        "context_length": config["context_length"],
        "max_total_num_tokens": config["max_total_tokens"],
        "page_size": config["page_size"],
    })
    validate_admission(validate_workload(warmup), warmup, {
        "context_length": config["context_length"],
        "max_total_num_tokens": config["max_total_tokens"],
        "page_size": config["page_size"],
    })
    validate_shapes(shapes, {
        "context_length": config["context_length"],
        "max_total_num_tokens": config["max_total_tokens"],
        "page_size": config["page_size"],
    })
    if workload.get("purpose") != "formal" or workload.get("formal_protocol_accepted") is not True:
        raise ValueError("Order-balanced repeats require the frozen formal workload")
    return release, config, workload, warmup, shapes, known_orchestration_drift


def write_batch_summary(batch: Path, order: list[str], results: list[dict], status: str, error: str | None = None) -> None:
    signatures = [canonical_digest(result["signature"])
                  for result in results if "signature" in result]
    save_json(batch / "summary.json", {
        "status": status,
        "policies": order,
        "runs": results,
        "all_protocol_checks_passed": status == "completed" and all(
            result.get("protocol_integrity_passed", False) for result in results
        ),
        "all_effective_signatures_equal": (
            len(signatures) == len(results) == len(order) and len(set(signatures)) == 1
        ),
        "error": error,
    })


async def run_batch(config_path: Path, config: dict, workload: dict, warmup: dict,
                    shapes: dict, batch: Path, order: list[str], ready_timeout: float) -> list[dict]:
    batch.mkdir(parents=False, exist_ok=False)
    save_json(batch / "suite.json", {
        "status": "running", "purpose": "order_balanced_repeat",
        "policies": order, "config_sha256": digest_file(config_path),
        "workload_sha256": canonical_digest(workload),
        "warmup_sha256": canonical_digest(warmup),
    })
    expected_signature = None
    results = []
    try:
        for index, policy in enumerate(order):
            output = batch / f"{index + 1:02d}_{policy}"
            expected_signature = await run_once(
                config, config_path, workload, warmup, policy, output,
                expected_signature, ready_timeout, shapes,
            )
            audit = audit_run(output)
            save_json(output / "integrity.json", audit)
            results.append(audit)
            if not audit["protocol_integrity_passed"] or not audit["post_flush_native_metrics_empty"] \
                    or not audit["cached_tokens_all_known"]:
                raise ValueError(f"Integrity audit failed for {policy}: {audit['integrity_errors']}")
            save_json(batch / "suite.json", {
                "status": "running", "purpose": "order_balanced_repeat",
                "policies": order, "config_sha256": digest_file(config_path),
                "workload_sha256": canonical_digest(workload),
                "warmup_sha256": canonical_digest(warmup),
                "runs": [{"policy": row["policy"], "path": f"{i + 1:02d}_{row['policy']}", "status": "completed"}
                         for i, row in enumerate(results)],
            })
        write_batch_summary(batch, order, results, "completed")
        save_json(batch / "suite.json", {**load(batch / "suite.json"), "status": "completed"})
        return results
    except BaseException as error:
        write_batch_summary(batch, order, results, "failed", repr(error))
        save_json(batch / "suite.json", {**load(batch / "suite.json"), "status": "failed", "error": repr(error)})
        raise


async def execute(args, output: Path) -> None:
    original_config_path = args.config.resolve()
    workload_path = args.workload.resolve()
    warmup_path = args.warmup.resolve()
    shape_path = args.shape_warmup.resolve()
    release_path = args.release.resolve()
    for path in (original_config_path, workload_path, warmup_path, shape_path, release_path):
        if not path.is_file() or not path.is_relative_to(ROOT):
            raise ValueError(f"Input must be an existing file inside experiment root: {path}")

    config_path, model_relocation = relocate_model_config(original_config_path, output)
    release, config, workload, warmup, shapes, known_orchestration_drift = validate_frozen_inputs(
        config_path, workload_path, warmup_path, shape_path, release_path,
        output / "release_for_repeat.json",
    )
    metadata = {
        "status": "running", "purpose": "order_balanced_lru_slru_repeat",
        "started_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "orders": [["lru", "slru"], ["slru", "lru"]],
        "release": str(release_path.relative_to(ROOT)),
        "release_sha256": digest_file(release_path),
        "release_for_repeat_sha256": digest_file(output / "release_for_repeat.json"),
        "known_orchestration_drift": known_orchestration_drift,
        "runner_sha256": digest_file(Path(__file__).resolve()),
        "model_relocation": model_relocation,
        "original_config": str(original_config_path.relative_to(ROOT)),
        "config": str(config_path.relative_to(ROOT)),
        "workload": str(workload_path.relative_to(ROOT)),
        "warmup": str(warmup_path.relative_to(ROOT)),
        "shape_warmup": str(shape_path.relative_to(ROOT)),
        "input_sha256": {
            "config": digest_file(config_path),
            "workload": digest_file(workload_path),
            "warmup": digest_file(warmup_path),
            "shape_warmup": digest_file(shape_path),
        },
        "frozen_original_release_signature": release["effective_signature"],
        "batches": [],
    }
    save_json(output / "batch.json", metadata)
    try:
        for index, order in enumerate((["lru", "slru"], ["slru", "lru"]), start=1):
            batch = output / f"{index:02d}_{'_'.join(order)}"
            results = await run_batch(config_path, config, workload, warmup, shapes, batch, order, args.ready_timeout)
            metadata["batches"].append({
                "path": str(batch.relative_to(ROOT)), "order": order,
                "status": "completed", "runs": results,
            })
            save_json(output / "batch.json", metadata)
        metadata["status"] = "completed"
        metadata["finished_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save_json(output / "batch.json", metadata)
    except BaseException as error:
        metadata["status"] = "failed"
        metadata["error"] = repr(error)
        metadata["finished_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save_json(output / "batch.json", metadata)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    root = ROOT / "data/workloads/exploration_1h_v4"
    parser.add_argument("--config", type=Path, default=root / "server.json")
    parser.add_argument("--workload", type=Path, default=root / "evaluation.json")
    parser.add_argument("--warmup", type=Path, default=ROOT / "data/workloads/smoke_protocol_v1/manifest.json")
    parser.add_argument("--shape-warmup", type=Path, default=root / "shape_warmup.json")
    parser.add_argument("--release", type=Path, default=ROOT / "results/exploration/20260927T163049Z_931188f1/release.json")
    parser.add_argument("--ready-timeout", type=float, default=3600)
    args = parser.parse_args()
    os.umask(0o077)
    output = ROOT / "results/order_balanced" / (
        datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    )
    output.mkdir(parents=True, exist_ok=False)
    with (ROOT / "runtime/suite.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        asyncio.run(execute(args, output))


if __name__ == "__main__":
    main()
