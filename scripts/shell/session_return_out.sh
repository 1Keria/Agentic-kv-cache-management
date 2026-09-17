# 小型重放默认输出目录。三份脚本都 source 这个文件。
# 覆盖：SESSION_RETURN_OUT_ROOT=/other/path
SESSION_RETURN_OUT_ROOT="${SESSION_RETURN_OUT_ROOT:-/share/dai-sys/zhoulongsheng/agentkv/experiments/session_return/replay_small}"
SESSION_RETURN_LATEST="$SESSION_RETURN_OUT_ROOT/LATEST"

session_return_init_run() {
  mkdir -p "$SESSION_RETURN_OUT_ROOT"
  RUN_DIR="$SESSION_RETURN_OUT_ROOT/run_$(date +%Y%m%d_%H%M%S)"
  mkdir -p "$RUN_DIR/server_dump" "$RUN_DIR/server_dump_node1" "$RUN_DIR/client"
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
  echo "找不到 $SESSION_RETURN_LATEST，请先在主节点起 glm51_session_return_node0.sh。" >&2
  return 1
}
