#!/usr/bin/env python3
"""Download SkillsBench with-skills llm_trajectory.jsonl for GLM-5.1 / V4-Flash / V4-Pro."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from huggingface_hub import list_repo_tree

REPO = "benchflow/skillsbench-leaderboard"
PREFIX = "submissions/skillsbench/v1.1"
CONFIGS = [
    "openhands-with-skills__glm-glm-5.1-src-runner04-20260609",
    "openhands-with-skills__glm-glm-5.1",
    "openhands-with-skills__deepseek-deepseek-v4-flash-src-runner03",
    "openhands-with-skills__deepseek-deepseek-v4-flash-src-runner05-20260610",
    "openhands-with-skills__deepseek-deepseek-v4-flash",
    "openhands-with-skills__deepseek-deepseek-v4-pro-src-runner03",
    "openhands-with-skills__deepseek-deepseek-v4-pro",
]
WORKERS = 12
MANIFEST_NAME = "download_manifest.json"


def collect_files() -> list[tuple[str, int]]:
    files: list[tuple[str, int]] = []
    for cfg in CONFIGS:
        path_in_repo = f"{PREFIX}/{cfg}"
        print(f"[list] {cfg}", flush=True)
        n_llm = 0
        for item in list_repo_tree(REPO, repo_type="dataset", path_in_repo=path_in_repo, recursive=True):
            p = getattr(item, "path", "")
            if not p.endswith("llm_trajectory.jsonl"):
                continue
            size = int(getattr(item, "size", 0) or 0)
            files.append((p, size))
            n_llm += 1
        print(f"       llm_trajectory={n_llm}", flush=True)
    return files


def already_ok(local: Path, size: int) -> bool:
    if not local.is_file():
        return False
    got = local.stat().st_size
    if size > 0:
        return got == size
    return got > 0


def download_one(filename: str, size: int, dest: Path) -> str:
    local = dest / filename
    if already_ok(local, size):
        return "skip"
    local.parent.mkdir(parents=True, exist_ok=True)
    tmp = local.with_suffix(local.suffix + ".part")
    url = (
        "https://huggingface.co/datasets/"
        f"{REPO}/resolve/main/{urllib.parse.quote(filename)}"
    )
    last_err: Exception | None = None
    for attempt in range(8):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "agentkv-skillsbench/1.0"},
            )
            with urllib.request.urlopen(req, timeout=300) as resp, tmp.open("wb") as out:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
            if size > 0 and tmp.stat().st_size != size:
                raise IOError(f"size mismatch {tmp.stat().st_size} != {size}")
            tmp.replace(local)
            return "ok"
        except urllib.error.HTTPError as exc:
            last_err = exc
            wait = 45 if exc.code == 429 else 3 * (attempt + 1)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            wait = 5 * (attempt + 1)
        if tmp.exists():
            tmp.unlink()
        time.sleep(wait)
    raise RuntimeError(f"{filename}: {last_err}")


def main() -> int:
    dest = Path(sys.argv[1] if len(sys.argv) > 1 else "third_party/skillsbench").resolve()
    dest.mkdir(parents=True, exist_ok=True)
    manifest = dest / MANIFEST_NAME
    if manifest.is_file() and "--refresh" not in sys.argv:
        files = [(p, int(s)) for p, s in json.loads(manifest.read_text())]
        print(f"[list] reuse {manifest} ({len(files)} files)", flush=True)
    else:
        files = collect_files()
        manifest.write_text(json.dumps(files, indent=2))
    total_bytes = sum(sz for _, sz in files)
    print(f"[plan] {len(files)} files, {total_bytes / 1024**3:.2f} GB", flush=True)

    done = skip = fail = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(download_one, name, size, dest): (name, size) for name, size in files}
        for i, fut in enumerate(as_completed(futs), 1):
            name, _size = futs[fut]
            try:
                status = fut.result()
            except Exception as exc:  # noqa: BLE001
                fail += 1
                print(f"[fail] {name}: {exc}", flush=True)
                continue
            if status == "skip":
                skip += 1
            else:
                done += 1
            if i % 10 == 0 or i == len(files):
                print(
                    f"[prog] {i}/{len(files)} done={done} skip={skip} fail={fail} {time.time() - t0:.0f}s",
                    flush=True,
                )
    print(f"[done] dest={dest} done={done} skip={skip} fail={fail} {time.time() - t0:.0f}s", flush=True)
    return 1 if fail else 0


if __name__ == "__main__":
    os.environ.setdefault("http_proxy", "http://127.0.0.1:7890")
    os.environ.setdefault("https_proxy", "http://127.0.0.1:7890")
    os.environ.setdefault("HTTP_PROXY", "http://127.0.0.1:7890")
    os.environ.setdefault("HTTPS_PROXY", "http://127.0.0.1:7890")
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    raise SystemExit(main())
