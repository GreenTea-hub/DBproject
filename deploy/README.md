# 部署手册（负责人：P5；从空白虚拟机到系统可访问）

> 目标环境：Ubuntu 22.04 LTS（虚拟机 4 核 / 8 GB），Neo4j 5.x 社区版 tar 包 + Flask + Gunicorn。
> 对外只开放 **5000**；7474 与 7687 不对外开放，只允许本机访问。

## 0. 前置检查

```bash
lsb_release -a            # Ubuntu 22.04
free -h                   # 建议 8 GB
ip addr                   # 记下本机 IP，虚拟机用桥接模式，Windows 宿主机要能 ping 通
```

## 1. 安装 JDK 17（Neo4j 运行依赖）

```bash
sudo apt update
sudo apt install -y openjdk-17-jre-headless
java -version
```

## 2. 安装 Neo4j 5.x（tar 包）

```bash
cd /opt
sudo wget https://dist.neo4j.org/neo4j-community-5.23.0-unix.tar.gz
sudo tar -xzf neo4j-community-5.23.0-unix.tar.gz
sudo mv neo4j-community-5.23.0 neo4j
sudo useradd -r -s /bin/false neo4j || true
sudo chown -R neo4j:neo4j /opt/neo4j
```

编辑 `/opt/neo4j/conf/neo4j.conf`（关键三行）：

```properties
server.default_listen_address=127.0.0.1
server.memory.heap.initial_size=2g
server.memory.heap.max_size=2g
server.memory.pagecache.size=1g
```

```bash
sudo -u neo4j /opt/neo4j/bin/neo4j-admin dbms set-initial-password '换成你的密码'
sudo -u neo4j /opt/neo4j/bin/neo4j start
sleep 20
cypher-shell -u neo4j -p '换成你的密码' "RETURN 1;"
```

> 监听地址设为 127.0.0.1 后，Browser（7474）也只能在服务器上用 SSH 隧道访问，这是刻意为之。

## 3. GDS 插件（P4 需要）

```bash
# 版本必须与 Neo4j 主版本一致：5.23.0 -> 5.23.0
sudo wget -P /opt/neo4j/plugins https://github.com/neo4j/graph-data-science/releases/download/2.13.2/neo4j-graph-data-science-2.13.2.jar
```

在 neo4j.conf 加一行后重启：

```properties
dbms.security.procedures.unrestricted=gds.*
```

装不上时走降级方案：用 Cypher 计算度数中心性等近似指标，报告里如实说明环境限制（见分工方案风险表）。

## 4. 部署应用

```bash
sudo apt install -y python3.11 python3.11-venv git
sudo mkdir -p /opt/sanguo-graph && sudo chown $USER /opt/sanguo-graph
git clone <仓库地址> /opt/sanguo-graph
cd /opt/sanguo-graph
python3.11 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env && vi .env        # 填 NEO4J_PASSWORD，MOCK_DATA 先留 1，联调后再改 0
```

## 5. 建库并导入数据

```bash
./venv/bin/python scripts/build_graph.py      # 建约束 + 导入 + 数量核对
./venv/bin/python scripts/build_graph.py --check
```

## 6. 启动服务

```bash
# 前台试跑
./venv/bin/python app.py
# 生产：Gunicorn
./venv/bin/gunicorn -c deploy/gunicorn.conf.py "app:create_app()"
# 或注册为 systemd 服务
sudo cp deploy/sanguo.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now sanguo
```

## 7. 防火墙

```bash
sudo ufw allow 22/tcp
sudo ufw allow 5000/tcp
sudo ufw deny 7474/tcp
sudo ufw deny 7687/tcp
sudo ufw enable && sudo ufw status
```

## 8. 验收

```bash
curl http://127.0.0.1:5000/api/health
# Windows 宿主机浏览器访问 http://<服务器IP>:5000/
python scripts/smoke.py
```

冒烟全绿、Windows 端能打开首页、关系图能渲染，即部署完成。把这一步的踩坑记到 `docs/deploy.md`。
