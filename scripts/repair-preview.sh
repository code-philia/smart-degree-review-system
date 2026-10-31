#!/usr/bin/env bash
set -euo pipefail

# Starts an isolated local preview of the repair-suggestion work.  It never
# reads or writes the production database and it only binds 127.0.0.1.

readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly WORKSPACE_ROOT="$(cd "$REPO_ROOT/.." && pwd)"
readonly PREVIEW_ROOT="${REPAIR_PREVIEW_ROOT:-$WORKSPACE_ROOT/runtime/repair-preview}"
readonly PREVIEW_DB="$PREVIEW_ROOT/app.sqlite"
readonly ARCHIVE_DB="$WORKSPACE_ROOT/runtime/repair-batch-20261021-adaptive-v3.sqlite"
readonly MODEL_ENV="$WORKSPACE_ROOT/config/sjtu.env"
readonly NODE_BIN="$WORKSPACE_ROOT/envs/node-v22.23.2/bin/node"
readonly PYTHON_BIN="$WORKSPACE_ROOT/envs/six-rules/bin/python"
readonly BACKEND_PORT="${REPAIR_PREVIEW_BACKEND_PORT:-3001}"
readonly FRONTEND_PORT="${REPAIR_PREVIEW_FRONTEND_PORT:-5174}"
readonly PREVIEW_HOST="${REPAIR_PREVIEW_HOST:-127.0.0.1}"
readonly BACKEND_PID_FILE="$PREVIEW_ROOT/backend.pid"
readonly FRONTEND_PID_FILE="$PREVIEW_ROOT/frontend.pid"
readonly BACKEND_LOG="$PREVIEW_ROOT/backend.log"
readonly FRONTEND_LOG="$PREVIEW_ROOT/frontend.log"

# Keep the complete isolated preview configuration in one external file. The
# wrapper still overrides ports and storage paths below, but model credentials,
# ledger, cache and model-runtime settings must reach the backend child process.
if [[ -r "$PREVIEW_ROOT/backend.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$PREVIEW_ROOT/backend.env"
  set +a
fi

usage() {
  cat <<'EOF'
Usage: scripts/repair-preview.sh [start|stop|status|reset]

  start   Start the isolated preview (default).  Reuses its existing preview DB.
  stop    Stop only processes started by this script.
  status  Show process and HTTP health status.
  reset   Back up the preview DB, recreate it from the archive suggestion DB,
          and start again.  Existing preview uploads and generated suggestions
          remain in the timestamped backup under runtime/repair-preview/backups/.

Environment overrides:
  REPAIR_PREVIEW_ROOT, REPAIR_PREVIEW_BACKEND_PORT, REPAIR_PREVIEW_FRONTEND_PORT
EOF
}

fail() { printf 'repair-preview: %s\n' "$*" >&2; exit 1; }
info() { printf 'repair-preview: %s\n' "$*"; }

pid_is_running() {
  local pid="$1"
  [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null
}

pid_from_file() {
  local file="$1"
  [[ -f "$file" ]] || return 1
  tr -d '[:space:]' < "$file"
}

stop_process() {
  local label="$1" pid_file="$2" expected="$3" pid
  pid="$(pid_from_file "$pid_file" || true)"
  [[ -n "$pid" ]] || return 0
  if ! pid_is_running "$pid"; then
    rm -f "$pid_file"
    return 0
  fi
  local command
  command="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
  [[ "$command" == *"$expected"* ]] || fail "拒绝停止 $label：PID $pid 不是此预览进程"
  kill "$pid"
  for _ in {1..20}; do
    pid_is_running "$pid" || { rm -f "$pid_file"; return 0; }
    sleep 0.25
  done
  fail "$label 未能在 5 秒内停止（PID $pid）"
}

clear_stale_pid_files() {
  local pid_file pid
  for pid_file in "$BACKEND_PID_FILE" "$FRONTEND_PID_FILE"; do
    pid="$(pid_from_file "$pid_file" || true)"
    [[ -n "$pid" ]] || continue
    if ! pid_is_running "$pid"; then
      rm -f "$pid_file"
      info "已清理失效的 PID 记录：$pid_file"
    fi
  done
}

port_is_listening() {
  local port="$1"
  ss -ltn "( sport = :$port )" 2>/dev/null | awk 'NR > 1 { found = 1 } END { exit found ? 0 : 1 }'
}

assert_port_available() {
  local port="$1" label="$2"
  if port_is_listening "$port"; then
    fail "$label 端口 $port 已被占用；请先执行 stop 或改用端口环境变量"
  fi
}

listener_pid() {
  local port="$1"
  ss -ltnp "( sport = :$port )" 2>/dev/null \
    | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' | head -n 1
}

check_prerequisites() {
  [[ -x "$NODE_BIN" ]] || fail "缺少 Node：$NODE_BIN"
  [[ -x "$PYTHON_BIN" ]] || fail "缺少六规则 Python：$PYTHON_BIN"
  [[ -f "$ARCHIVE_DB" ]] || fail "缺少归档建议数据库：$ARCHIVE_DB"
  [[ -f "$MODEL_ENV" ]] || fail "缺少模型配置：$MODEL_ENV"
  "$PYTHON_BIN" -c 'import fitz' >/dev/null 2>&1 || fail "六规则 Python 缺少 PyMuPDF"
  [[ -d "$REPO_ROOT/backend/node_modules" ]] || fail "后端依赖未安装"
  [[ -d "$REPO_ROOT/frontend/node_modules" ]] || fail "前端依赖未安装"
}

load_model_configuration() {
  set -a
  # shellcheck disable=SC1090
  . "$MODEL_ENV"
  set +a
  [[ -n "${SJTU_API_KEY:-}" ]] || fail '模型配置缺少 SJTU_API_KEY'
  [[ -n "${SJTU_API_BASE_URL:-}" ]] || fail '模型配置缺少 SJTU_API_BASE_URL'
  [[ -n "${SJTU_API_MODEL:-}" ]] || fail '模型配置缺少 SJTU_API_MODEL'
}

initialize_database() {
  mkdir -p "$PREVIEW_ROOT" "$PREVIEW_ROOT/paper-lint-reports" "$PREVIEW_ROOT/paper-lint-jobs"
  if [[ ! -f "$PREVIEW_DB" ]]; then
    cp --preserve=mode,timestamps "$ARCHIVE_DB" "$PREVIEW_DB"
    info '已由归档建议数据库创建新的预览副本'
    ARC_DB_FILE="$PREVIEW_DB" ARC_ALLOW_DEMO_SEED=1 "$NODE_BIN" \
      "$REPO_ROOT/backend/src/database/seed_demo_db.js" >/dev/null
    info '已写入演示登录账号；原归档数据库未修改'
  fi
}

start_backend() {
  assert_port_available "$BACKEND_PORT" '后端'
  (
    cd "$REPO_ROOT/backend"
    export PORT="$BACKEND_PORT"
    export ARC_LISTEN_HOST="$PREVIEW_HOST"
    export ARC_DB_FILE="$PREVIEW_DB"
    export PAPER_LINT_REPORTS_DIR="$PREVIEW_ROOT/paper-lint-reports"
    export PAPER_LINT_JOBS_DIR="$PREVIEW_ROOT/paper-lint-jobs"
    export ARCHIVE_SCAN_ROOT="$WORKSPACE_ROOT/data/archive479"
    export FIVE_RULE_PYTHON="$PYTHON_BIN"
    export SIX_RULE_PYTHON="$PYTHON_BIN"
    export REPAIR_EVIDENCE_PYTHON="$PYTHON_BIN"
    setsid -f "$NODE_BIN" src/index.js </dev/null >"$BACKEND_LOG" 2>&1
  )
  for _ in {1..20}; do
    if curl -fsS "http://127.0.0.1:$BACKEND_PORT/api/health" >/dev/null 2>&1; then
      listener_pid "$BACKEND_PORT" > "$BACKEND_PID_FILE"
      return 0
    fi
    sleep 0.25
  done
  sed -n '1,120p' "$BACKEND_LOG" >&2 || true
  fail "后端未在 127.0.0.1:$BACKEND_PORT 就绪；请查看 $BACKEND_LOG"
}

start_frontend() {
  assert_port_available "$FRONTEND_PORT" '前端'
  (
    cd "$REPO_ROOT/frontend"
    export ARC_WEB_PORT="$BACKEND_PORT"
    setsid -f "$NODE_BIN" node_modules/vite/bin/vite.js --host "$PREVIEW_HOST" --port "$FRONTEND_PORT" --strictPort \
      </dev/null >"$FRONTEND_LOG" 2>&1
  )
  for _ in {1..20}; do
    if curl -fsS "http://127.0.0.1:$FRONTEND_PORT/" >/dev/null 2>&1; then
      listener_pid "$FRONTEND_PORT" > "$FRONTEND_PID_FILE"
      return 0
    fi
    sleep 0.25
  done
  sed -n '1,120p' "$FRONTEND_LOG" >&2 || true
  fail "前端未在 127.0.0.1:$FRONTEND_PORT 就绪；请查看 $FRONTEND_LOG"
}

status() {
  local backend_pid frontend_pid
  backend_pid="$(pid_from_file "$BACKEND_PID_FILE" || true)"
  frontend_pid="$(pid_from_file "$FRONTEND_PID_FILE" || true)"
  if [[ -n "$backend_pid" ]] && pid_is_running "$backend_pid"; then
    if curl -fsS "http://127.0.0.1:$BACKEND_PORT/api/health" >/dev/null 2>&1; then
      info "后端运行且健康：PID $backend_pid，http://$PREVIEW_HOST:$BACKEND_PORT"
    else
      info "后端进程存在但健康检查失败：PID $backend_pid"
    fi
  else
    info '后端未运行'
  fi
  if [[ -n "$frontend_pid" ]] && pid_is_running "$frontend_pid"; then
    if curl -fsS "http://127.0.0.1:$FRONTEND_PORT/" >/dev/null 2>&1; then
      info "前端运行且健康：PID $frontend_pid，http://$PREVIEW_HOST:$FRONTEND_PORT"
    else
      info "前端进程存在但页面检查失败：PID $frontend_pid"
    fi
  else
    info '前端未运行'
  fi
}

stop() {
  stop_process '前端' "$FRONTEND_PID_FILE" 'node_modules/vite/bin/vite.js'
  stop_process '后端' "$BACKEND_PID_FILE" 'src/index.js'
  info '预览服务已停止'
}

reset() {
  stop
  if [[ -f "$PREVIEW_DB" ]]; then
    local backup_dir="$PREVIEW_ROOT/backups"
    mkdir -p "$backup_dir"
    local stamp
    stamp="$(date +%Y%m%d-%H%M%S)"
    local backup_path="$backup_dir/$stamp"
    mkdir -p "$backup_path"
    mv "$PREVIEW_DB" "$backup_path/app.sqlite"
    for directory in paper-lint-reports paper-lint-jobs; do
      if [[ -d "$PREVIEW_ROOT/$directory" ]]; then
        mv "$PREVIEW_ROOT/$directory" "$backup_path/$directory"
      fi
    done
    info "旧预览数据库与临时上传文件已备份至 $backup_path"
  fi
  initialize_database
}

start() {
  check_prerequisites
  load_model_configuration
  clear_stale_pid_files
  if [[ -f "$BACKEND_PID_FILE" ]] || [[ -f "$FRONTEND_PID_FILE" ]]; then
    status
    fail '已有预览进程记录；请先执行 stop，或确认进程仍在运行'
  fi
  initialize_database
  assert_port_available "$BACKEND_PORT" '后端'
  assert_port_available "$FRONTEND_PORT" '前端'
  start_backend
  if ! start_frontend; then
    stop_process '后端' "$BACKEND_PID_FILE" 'src/index.js' || true
    exit 1
  fi
  info "预览已启动：http://$PREVIEW_HOST:$FRONTEND_PORT"
  info '演示账号：school_admin01 / ArcDemo123!'
}

command="${1:-start}"
case "$command" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  reset) reset; start ;;
  -h|--help|help) usage ;;
  *) usage >&2; exit 2 ;;
esac
