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
- 解决：**已由 P5 把 ECharts 5.5.1 提交进 `static/vendor/`**（md5 `ef12c5c6…`），拉到仓库即有；
  只有当 `git status` 显示该文件缺失时才需要重新下载（见 `static/vendor/README.md`）。
- 耗时：5 分钟（含一次断网彩排）

### 5. 生产环境把 `.env.example` 直接复制成 `.env` 用，页面能看到调试报错堆栈
- 现象：浏览器上直接显示 Python traceback，或数据库连不上却仍显示样例数据。
- 原因：`.env.example` 是开发模板，`FLASK_DEBUG=1`、`MOCK_DATA=1`；生产要反过来。
- 解决：生产 `.env` 必须是 `FLASK_DEBUG=0`、`MOCK_DATA=0`，并填真实的 `NEO4J_PASSWORD`；
  `deploy/install.sh` 自动生成的就是生产值，手工部署时别直接 `cp .env.example .env` 了事。
- 耗时：10 分钟（先怀疑数据库，最后发现是配置）

### 6. 页面样式或脚本改了但浏览器看不出变化
- 现象：`style.css`、`graph.js` 改完刷新页面没反应，甚至关系图工具栏不出现。
- 原因：Flask 静态文件带缓存头，浏览器复用了旧文件。
- 解决：`Ctrl + F5` 强制刷新；确认 URL 没被 CDN 缓存（本项目的 ECharts 已本地化，不存在这个问题）。
- 耗时：3 分钟
