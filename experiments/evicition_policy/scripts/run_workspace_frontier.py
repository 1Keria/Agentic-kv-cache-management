#!/usr/bin/env python3
"""Run the independently frozen arrived-request workspace ablation."""

import argparse
from pathlib import Path

import run_checkpoint_frontier as runner
from workspace_checkpoint import WorkspaceInputReplay


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runner.SOURCES = (*runner.SOURCES, "workspace_checkpoint.py", "run_workspace_frontier.py")
    runner.ObservedInputReplay = WorkspaceInputReplay
    runner.run(args)
