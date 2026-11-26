# 三国演义人物关系图谱

数据库系统原理课程设计（2026—2027 学年第一学期，第 24 组）——以《三国演义》一百二十回为语料，
抽取人物、阵营、事件及其关系，用 **Neo4j 图数据库** 存储与查询，**Flask** 提供 Web 服务，
浏览器端用 **ECharts** 呈现可交互的人物关系网络。

```
浏览器（Windows，独立 IP）
      │  HTTP / JSON
      ▼
Flask 应用（Linux，Gunicorn，5000）
      │  Cypher（Bolt 7687，仅本机）
      ▼
Neo4j 5.x（与 Flask 同机部署）
```

## 快速开始（本地）

```bash
python -m venv venv
source venv/bin/activate           # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
python app.py                      # http://127.0.0.1:5000
```

默认 `MOCK_DATA=1`：不连数据库，接口返回写死的样例数据（契约与真实一致），
前端和后端可以同时开工。数据库连通后把 `.env` 里改成 `MOCK_DATA=0` 即可无缝切换。

```bash
python scripts/extract_mentions.py --validate   # 数据质检（P1）
python scripts/build_graph.py                   # 建约束 + 导入 + 核对（P2）
python scripts/smoke.py                         # 冒烟检查（全组，合并前必跑）
```

没装 Neo4j 的机器（或答辩机上不许装服务）用仓库自带的内嵌版，真内核、标准 Bolt 端口，
应用与导入脚本都不用改：

```bash
cd dev/neo4j-embed && mvn -q compile exec:java   # 需要 JDK 17 + Maven，监听 7687 / 7474
```

## 目录结构

```
app.py                 应用入口：创建 Flask 实例、注册蓝图、统一错误处理（P3）
config.py              读取 .env 配置（P3）
.env.example           配置模板，真实 .env 不进仓库
requirements.txt       依赖清单（只由 P3 修改）
graph/                 数据访问层：全部 Cypher 写在这里
  driver.py            连接与请求级会话管理（P3）
  queries_person.py    人物、搜索、子图（P3）
  queries_event.py     事件、时间线（P2）
  queries_algo.py      最短路、影响力、社区发现、小世界（P4）
  queries_admin.py     增删改、合并重复人物（P2）
  schema.cypher        约束与索引，可重复执行（P2）
  mock.py              占位数据（P3）
views/                 接口层：Flask 蓝图
  __init__.py          蓝图注册表（P3，只允许末尾追加一行）
  pages.py             页面路由（P5）
  api_person.py        人物接口（P3）
  api_event.py         事件接口（P2）
  api_algo.py          算法接口（P4）
  api_admin.py         管理接口（P2）
utils/                 公共工具：response / serialize / validators（P3）
templates/             Jinja2 模板，base.html 为全站母版（P5）
static/                css / js / vendor（ECharts）
data/                  人物词典、关系、事件（P1）；raw/ 与 build/ 不入仓库
scripts/               抽取、导入、建库、冒烟（分属 P1/P2/P3）
deploy/                部署脚本与手册（P5）
docs/                  数据、模型、接口、算法、部署文档
```

## 协作规范（摘要，全文见《小组协作与分工方案》）

- **主干 main 不允许直接推送**，全部通过合并请求进入；
- **每人一条固定分支**：`dev-p1` … `dev-p5`；
- 提交说明格式 `类型：内容`，类型取 `feat / fix / docs / refactor / chore`；
- **每周日 20:00 前**推送并发起 PR，20:00—20:40 由轮值负责人（P1→P2→P3→P4→P5）评审合并、
  重建数据库、跑冒烟、打 tag、写变更记录；
- 合并前冒烟必须全绿；主干任何时刻都要能启动；
- 文件归属见上表，改别人的文件先沟通，并以 PR 形式由该文件负责人批准。

## 文档

- [数据说明](docs/data.md) · [图模型](docs/model.md) · [接口契约](docs/api.md) · [算法与对比](docs/algo.md)
- [部署手册](deploy/README.md) · [踩坑记录](docs/deploy.md) · [变更记录](docs/changelog.md) · [贡献记录](docs/contribution.md)

## 当前状态

| 项 | 状态 |
|---|---|
| 仓库骨架 | 已完成（v0.1-skeleton） |
| 接口契约 | 已冻结，待全组确认 |
| 数据 | 已完成首版：120 回切分、179 人、333 条关系、83 个事件（质检 0 错误） |
| 数据库 | 已跑通：179 人 / 120 回 / 83 事件 / 333 关系 / 51 地点，导入后自动对账 |
| 部署 | 未开始（第 15 周） |
