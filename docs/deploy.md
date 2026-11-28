# 部署踩坑记录（负责人：P5，部署步骤有变动时更新）

> 正式步骤见 `deploy/README.md`，本文件只记"文档里没写、但实际会卡住"的地方。
> 每人第 15 周前都要在一台干净虚拟机上独立部署一次，把自己的坑追加到这里。

## 模板

```
### 现象
### 原因
### 解决
### 耗时
```

## 已知问题

### 1. Windows 宿主机访问不了 http://<服务器IP>:5000
- 原因：虚拟机用了 NAT 模式，或 ufw 未放行 5000。
- 解决：虚拟机网络改为桥接；`sudo ufw allow 5000/tcp`；确认 Flask 监听 `0.0.0.0` 而不是 `127.0.0.1`。

### 2. Neo4j 启动后立即退出
- 原因：JDK 版本不对（Neo4j 5 需要 JDK 17），或 heap 设得比内存还大。
- 解决：`java -version` 确认 17；`neo4j.conf` 里 heap 2g、pagecache 1g，虚拟机至少 8 GB。

### 3. 导入报 "Constraint already exists"
- 原因：手动跑过旧版建库语句。
- 解决：`schema.cypher` 全部是 `IF NOT EXISTS`，重复执行不报错；如仍报错，先 `SHOW CONSTRAINTS` 核对。

### 4. 页面能打开，关系图空白
- 原因：`static/vendor/echarts.min.js` 没放，且答辩环境无外网导致 CDN 也加载不到。
- 解决：提前把 ECharts 下载进 `static/vendor/`（见该目录 README），断网彩排一次。

### 5. 官网下载 Neo4j 返回 403（CloudFront "block access from your country"）
- 现象：`https://dist.neo4j.org/neo4j-community-5.26.0-unix.tar.gz` 直接 403，
  页面正文是 `The Amazon CloudFront distribution is configured to block access from your country`。
  换 `neo4j.com/artifact.php` 同样 403，换 http/ssh 端口也没用。
- 原因：Neo4j 的下载走 CloudFront，对部分地区整段拒绝，不是网络慢，也不是代理配置错。
- 解决：三条路，按可用性排序——
  1. 让有条件的同学/实验室机器下好 zip，走群共享目录分发（最稳，答辩前一周就做）；
  2. 用仓库里的 `dev/neo4j-embed`（官方 `neo4j-harness`，真内核 + 标准 Bolt，无需安装）；
  3. 从 Maven 镜像的 `org.neo4j` 构件自行拼装——不推荐，费时且容易漏包。
- 提醒：`dev/neo4j-embed` 只用于开发和验证，第 15 周的正式部署仍要用官方安装包。
