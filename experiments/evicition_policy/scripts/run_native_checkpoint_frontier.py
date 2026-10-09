#!/usr/bin/env python3
"""Run the frozen no-added-split checkpoint comparisons and workspace ablation."""

import argparse
from pathlib import Path

import run_checkpoint_frontier as runner
from native_checkpoint_frontier import NativeCheckpointFrontier
from workspace_checkpoint import WorkspaceInputReplay


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workspace", action="store_true")
    args = parser.parse_args()
    runner.RetainedFrontier = NativeCheckpointFrontier
    runner.SOURCES = (*runner.SOURCES, "native_checkpoint_frontier.py",
                      "workspace_checkpoint.py", "run_native_checkpoint_frontier.py")
    if args.workspace:
        runner.ObservedInputReplay = WorkspaceInputReplay
    runner.run(args)
