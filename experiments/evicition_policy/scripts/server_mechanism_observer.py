#!/usr/bin/env python3
"""Launch the separately verified official-wheel observation copy."""

import argparse
import json
import os
from pathlib import Path
import sys

from prepare_mechanism_observer import ROOT, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--policy", choices=["lru", "slru"], required=True)
    args = parser.parse_args()
    overlay = Path(os.environ["AGENTKV_MECHANISM_OVERLAY"]).resolve()
    if not overlay.is_relative_to(ROOT / "runtime"):
        raise ValueError("Overlay outside the experiment")
    lock = json.loads((overlay / "observation.lock.json").read_text())
    for relative, expected in lock["files"].items():
        if digest(overlay / "sglang" / relative) != expected["observed_sha256"]:
            raise ValueError(f"Observation source changed: {relative}")
    if digest(overlay / "sglang/srt/mem_cache/mechanism_observer.py") != lock["observer_sha256"]:
        raise ValueError("Installed observer changed")
    if os.environ.get("AGENTKV_EXPOSURE_BARRIER"):
        raise ValueError("Observation run must keep the native strategy")
    sys.path.insert(0, str(overlay))
    import sglang
    from server_command import build_command
    if not Path(sglang.__file__).resolve().is_relative_to(overlay):
        raise ValueError("Wrong SGLang import origin")
    config = json.loads(args.config.read_text())
    command = build_command(config, args.policy)
    print(json.dumps({"sglang_origin": sglang.__file__, "observation_only": True,
                      "overlay_lock_sha256": digest(overlay / "observation.lock.json"), "command": command}), flush=True)
    os.environ["PYTHONPATH"] = str(overlay)
    os.execv(sys.executable, command)


if __name__ == "__main__":
    main()
