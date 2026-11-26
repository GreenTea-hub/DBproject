#!/usr/bin/env bash
# 更新线上部署：拉代码 → 补依赖 → 重启 → 自检（负责人：P5）
#
# 用法（服务器上执行）：
#   bash deploy/update.sh                 # 更新到 main 最新
#   bash deploy/update.sh --ref v1.0      # 切到某个 tag（回滚也用它）
#   bash deploy/update.sh --dir /opt/sanguo-graph --skip-smoke
#
# 每次组内合并后由轮值负责人在服务器上跑一遍，冒烟不全绿就回滚。

set -euo pipefail

APP_DIR="/opt/sanguo-graph"
REF=""
SKIP_SMOKE=0
APP_USER="sanguo"
SERVICE_NAME="sanguo"

log()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[警告] %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m[失败] %s\033[0m\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref)        REF="${2:-}"; shift 2 ;;
    --dir)        APP_DIR="${2:-}"; shift 2 ;;
    --skip-smoke) SKIP_SMOKE=1; shift ;;
    -h|--help)    sed -n '2,12p' "$0"; exit 0 ;;
    *)            die "未知参数：$1（--help 查看用法）" ;;
  esac
done

[[ -d "$APP_DIR/.git" ]] || die "$APP_DIR 不是 git 仓库，请先跑 deploy/install.sh"
cd "$APP_DIR"

PREV_COMMIT="$(sudo -u "$APP_USER" git rev-parse --short HEAD)"
log "当前版本：$PREV_COMMIT"

log "拉取代码"
sudo -u "$APP_USER" git fetch --all --tags --prune
if [[ -n "$REF" ]]; then
  sudo -u "$APP_USER" git checkout -f "$REF"
else
  sudo -u "$APP_USER" git checkout main
  sudo -u "$APP_USER" git pull --ff-only
fi

log "同步依赖"
sudo -u "$APP_USER" ./venv/bin/pip install -q -r requirements.txt

log "重启服务"
sudo systemctl restart "$SERVICE_NAME"

log "等待健康检查"
OK=0
for i in $(seq 1 20); do
  if curl -fsS -o /dev/null --max-time 2 http://127.0.0.1:5000/api/health; then OK=1; break; fi
  sleep 1
done
if [[ $OK -eq 0 ]]; then
  sudo systemctl status "$SERVICE_NAME" --no-pager -l | tail -20 || true
  die "服务 20 秒内未起来。回滚：bash deploy/update.sh --ref $PREV_COMMIT"
fi
curl -s http://127.0.0.1:5000/api/health; echo

if [[ $SKIP_SMOKE -eq 0 ]]; then
  log "运行冒烟检查"
  if ! sudo -u "$APP_USER" ./venv/bin/python scripts/smoke.py; then
    die "冒烟未通过，立即回滚：bash deploy/update.sh --ref $PREV_COMMIT"
  fi
else
  warn "已跳过冒烟检查"
fi

log "更新完成：$PREV_COMMIT → $(sudo -u "$APP_USER" git rev-parse --short HEAD)"
