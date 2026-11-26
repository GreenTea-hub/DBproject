#!/usr/bin/env bash
# 一键部署脚本 —— 从空白 Ubuntu 22.04 到系统可访问（负责人：P5）
#
# 用法（在服务器上，用有 sudo 权限的普通用户执行）：
#   bash deploy/install.sh --password '你的Neo4j密码'
#
# 可选参数：
#   --password   Neo4j 初始密码（必填）
#   --repo       仓库地址，默认用本脚本所在仓库的 origin
#   --dir        安装目录，默认 /opt/sanguo-graph
#   --skip-neo4j 跳过 Neo4j 安装（已装过时用）
#
# 脚本可重复执行：已完成的步骤会自动跳过，不会覆盖已有数据库。
#
# 前置条件：Ubuntu 22.04、能连外网、当前用户有 sudo 权限、虚拟机内存建议 8 GB。

set -euo pipefail

APP_DIR="/opt/sanguo-graph"
NEO4J_HOME="/opt/neo4j"
NEO4J_VER="5.23.0"
GDS_VER="2.13.2"
NEO4J_PASSWORD=""
REPO_URL=""
SKIP_NEO4J=0
APP_USER="sanguo"
SERVICE_NAME="sanguo"

log()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[警告] %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m[失败] %s\033[0m\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --password)   NEO4J_PASSWORD="${2:-}"; shift 2 ;;
    --repo)       REPO_URL="${2:-}"; shift 2 ;;
    --dir)        APP_DIR="${2:-}"; shift 2 ;;
    --skip-neo4j) SKIP_NEO4J=1; shift ;;
    -h|--help)    sed -n '2,20p' "$0"; exit 0 ;;
    *)            die "未知参数：$1（--help 查看用法）" ;;
  esac
done

[[ -n "$NEO4J_PASSWORD" ]] || die "必须用 --password 指定 Neo4j 密码"
[[ $EUID -ne 0 ]] || warn "建议用普通用户执行（脚本内部自行 sudo），当前是 root"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
if [[ -z "$REPO_URL" && -d "$REPO_ROOT/.git" ]]; then
  REPO_URL="$(git -C "$REPO_ROOT" remote get-url origin || true)"
fi

# ---------------------------------------------------------------- 0. 系统检查
log "检查系统环境"
grep -qi "ubuntu" /etc/os-release || warn "非 Ubuntu 系统，脚本按 Ubuntu 22.04 编写，可能失败"
MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
[[ $MEM_MB -ge 3800 ]] || warn "内存仅 ${MEM_MB} MB，Neo4j 建议 8 GB，可能起不来"

log "安装系统依赖（JDK 17 / Python 3.11 / git / curl / ufw）"
sudo apt-get update -qq
sudo apt-get install -y -qq openjdk-17-jre-headless python3.11 python3.11-venv \
  python3.11-dev git curl ufw ca-certificates >/dev/null
java -version 2>&1 | head -1

# ---------------------------------------------------------------- 1. Neo4j
install_neo4j() {
  if [[ -x "$NEO4J_HOME/bin/neo4j" ]]; then
    log "Neo4j 已安装，跳过下载"
    return
  fi
  log "下载 Neo4j ${NEO4J_VER}（tar 包）"
  cd /tmp
  sudo curl -fsSL -o "neo4j-community-${NEO4J_VER}-unix.tar.gz" \
    "https://dist.neo4j.org/neo4j-community-${NEO4J_VER}-unix.tar.gz"
  sudo tar -xzf "neo4j-community-${NEO4J_VER}-unix.tar.gz" -C /opt
  sudo mv "/opt/neo4j-community-${NEO4J_VER}" "$NEO4J_HOME"
  id neo4j >/dev/null 2>&1 || sudo useradd -r -s /bin/false neo4j
  sudo chown -R neo4j:neo4j "$NEO4J_HOME"
}

configure_neo4j() {
  log "写入 Neo4j 配置（只监听本机，堆内存 2g）"
  local conf="$NEO4J_HOME/conf/neo4j.conf"
  # 先删掉同名旧配置，避免重复键
  sudo sed -i -E '/^(server\.default_listen_address|server\.memory\.heap\.initial_size|server\.memory\.heap\.max_size|server\.memory\.pagecache\.size|dbms\.security\.procedures\.unrestricted)=/d' "$conf"
  sudo tee -a "$conf" >/dev/null <<'CONF'

# ---- 由 deploy/install.sh 写入 ----
server.default_listen_address=127.0.0.1
server.memory.heap.initial_size=2g
server.memory.heap.max_size=2g
server.memory.pagecache.size=1g
dbms.security.procedures.unrestricted=gds.*
CONF
  sudo chown neo4j:neo4j "$conf"
}

init_neo4j_password() {
  log "初始化 Neo4j 密码"
  if sudo test -d "$NEO4J_HOME/data/dbms"; then
    warn "已存在账号数据，跳过密码初始化（忘记密码请查 deploy/README.md 附录）"
  else
    sudo -u neo4j "$NEO4J_HOME/bin/neo4j-admin" dbms set-initial-password "$NEO4J_PASSWORD"
  fi
}

install_gds() {
  local jar="$NEO4J_HOME/plugins/neo4j-graph-data-science-${GDS_VER}.jar"
  if sudo test -f "$jar"; then
    log "GDS 插件已存在，跳过"
    return
  fi
  log "安装 GDS 插件 ${GDS_VER}"
  sudo curl -fsSL -o "$jar" \
    "https://github.com/neo4j/graph-data-science/releases/download/${GDS_VER}/neo4j-graph-data-science-${GDS_VER}.jar" \
    || warn "GDS 下载失败：P4 的算法会退回 Cypher 近似实现，不算部署失败"
  sudo chown neo4j:neo4j "$jar" 2>/dev/null || true
}

start_neo4j() {
  log "启动 Neo4j"
  if sudo -u neo4j "$NEO4J_HOME/bin/neo4j" status 2>/dev/null | grep -q "running"; then
    sudo -u neo4j "$NEO4J_HOME/bin/neo4j" restart
  else
    sudo -u neo4j "$NEO4J_HOME/bin/neo4j" start
  fi

  log "等待 Bolt 端口 7687 就绪（最多 90 秒）"
  for i in $(seq 1 45); do
    if (exec 3<>/dev/tcp/127.0.0.1/7687) 2>/dev/null; then
      exec 3<&- 3>&-
      log "Neo4j 已就绪"
      return
    fi
    sleep 2
  done
  die "Neo4j 90 秒内未就绪，查看日志：sudo journalctl -u neo4j 或 $NEO4J_HOME/logs/neo4j.log"
}

if [[ $SKIP_NEO4J -eq 0 ]]; then
  install_neo4j
  configure_neo4j
  init_neo4j_password
  install_gds
  start_neo4j
fi

# ---------------------------------------------------------------- 2. 应用
log "部署应用到 $APP_DIR"
id "$APP_USER" >/dev/null 2>&1 || sudo useradd -r -m -s /bin/bash "$APP_USER"
sudo mkdir -p "$APP_DIR"

if [[ -d "$APP_DIR/.git" ]]; then
  log "目录已存在仓库，执行 git pull"
  sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only
else
  [[ -n "$REPO_URL" ]] || die "无法确定仓库地址，请用 --repo 指定"
  log "克隆 $REPO_URL"
  sudo rm -rf "$APP_DIR"
  sudo git clone "$REPO_URL" "$APP_DIR"
  sudo chown -R "$APP_USER:$APP_USER" "$APP_DIR"
fi

log "创建虚拟环境并安装依赖"
sudo -u "$APP_USER" python3.11 -m venv "$APP_DIR/venv"
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -q --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

log "生成 .env（生产模式：MOCK_DATA=0、DEBUG=0）"
sudo -u "$APP_USER" tee "$APP_DIR/.env" >/dev/null <<ENV
# 由 deploy/install.sh 生成，含密码，不要提交
FLASK_PORT=5000
FLASK_DEBUG=0
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=${NEO4J_PASSWORD}
MOCK_DATA=0
ENV
sudo chmod 600 "$APP_DIR/.env"

if [[ $SKIP_NEO4J -eq 0 ]]; then
  log "建库并导入数据（可重复执行）"
  ( cd "$APP_DIR" && sudo -u "$APP_USER" ./venv/bin/python scripts/build_graph.py ) \
    || warn "导入失败：数据文件可能还没就位，稍后手动执行 scripts/build_graph.py"
fi

# ---------------------------------------------------------------- 3. systemd
log "注册 systemd 服务"
sudo cp "$APP_DIR/deploy/sanguo.service" "/etc/systemd/system/${SERVICE_NAME}.service"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME" >/dev/null 2>&1 || true
sudo systemctl restart "$SERVICE_NAME"

# ---------------------------------------------------------------- 4. 防火墙
log "配置防火墙：只放行 22 / 5000"
sudo ufw allow 22/tcp   >/dev/null 2>&1 || true
sudo ufw allow 5000/tcp >/dev/null 2>&1 || true
sudo ufw deny  7474/tcp >/dev/null 2>&1 || true
sudo ufw deny  7687/tcp >/dev/null 2>&1 || true
sudo ufw --force enable >/dev/null 2>&1 || warn "ufw 启用失败，请手动执行 deploy/README.md 第 7 节"

# ---------------------------------------------------------------- 5. 验收
log "等待服务监听 5000 端口"
for i in $(seq 1 20); do
  if curl -fsS -o /dev/null --max-time 2 http://127.0.0.1:5000/api/health; then break; fi
  sleep 1
done

echo
curl -s http://127.0.0.1:5000/api/health || true
echo
SERVER_IP=$(hostname -I | awk '{print $1}')
cat <<DONE

部署完成。浏览器访问：http://${SERVER_IP}:5000/

后续操作：
  跑冒烟     cd ${APP_DIR} && ./venv/bin/python scripts/smoke.py
  看日志     sudo journalctl -u ${SERVICE_NAME} -f
  更新版本   bash ${APP_DIR}/deploy/update.sh
  换数据库密码 参见 deploy/README.md 附录

DONE
