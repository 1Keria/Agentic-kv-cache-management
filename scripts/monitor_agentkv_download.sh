#!/usr/bin/env bash
# Monitor the resumable Hugging Face dataset download without exposing credentials.
set -euo pipefail
DEST="${AGENTKV_DATASET_DIR:-/inspire/hdd/project/inference-chip/czxs25240022/datasets/agentkv-runtime}"
LOG="${AGENTKV_DOWNLOAD_LOG:-/tmp/agentkv-runtime-download.log}"

printf 'Time: '; date '+%F %T %Z'
printf 'Downloader: '
pgrep -af '[d]ownload_agentkv.py|[a]gentkv_download_once.py|[r]un_agentkv_download_forever.sh' || printf 'NOT RUNNING\n'
printf 'Dataset directory: '
du -sh "$DEST" 2>/dev/null || printf 'not found\n'
printf 'Free space: '
df -h "$DEST" 2>/dev/null | tail -1 || true
printf '\nLatest downloader events:\n'
grep -E 'Fetching [0-9]+ files:|DOWNLOAD_COMPLETE|RESTART|Traceback|Error|Retrying' "$LOG" 2>/dev/null | tail -5 || true
printf '\nActive partial downloads (.incomplete):\n'
find "$DEST/.cache/huggingface/download" -name '*.incomplete' -type f -printf '%T@ %s %p\n' 2>/dev/null \
  | sort -nr | head -5 \
  | awk '{printf "  %.2f GiB  %s\n", $2/1024/1024/1024, $3}' || true
