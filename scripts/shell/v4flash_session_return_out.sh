# GLM jsonl 在 V4 Flash 上采集。覆盖：
# SESSION_RETURN_OUT_ROOT=/other/path
REPO="${REPO:-/share/dai-sys/zhoulongsheng/agentkv}"
SESSION_RETURN_OUT_ROOT="${SESSION_RETURN_OUT_ROOT:-$REPO/experiments/session_return/replay_glm_on_v4flash}"
SESSION_RETURN_LATEST="$SESSION_RETURN_OUT_ROOT/LATEST"

session_return_init_run() {
  mkdir -p "$SESSION_RETURN_OUT_ROOT"
  RUN_DIR="$SESSION_RETURN_OUT_ROOT/run_$(date +%Y%m%d_%H%M%S)"
  mkdir -p "$RUN_DIR/server_dump" "$RUN_DIR/client"
  printf '%s\n' "$RUN_DIR" > "$SESSION_RETURN_LATEST"
  ln -sfn "$RUN_DIR" "$SESSION_RETURN_OUT_ROOT/latest"
}

session_return_load_run() {
  local i
  for i in $(seq 1 60); do
    if [[ -f "$SESSION_RETURN_LATEST" ]]; then
      RUN_DIR="$(cat "$SESSION_RETURN_LATEST")"
      if [[ -n "$RUN_DIR" && -d "$RUN_DIR" ]]; then
        return 0
      fi
    fi
    sleep 1
  done
  echo "找不到 $SESSION_RETURN_LATEST，请先起 v4flash_session_return.sh。" >&2
  return 1
}
