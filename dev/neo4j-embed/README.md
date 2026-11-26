# 内嵌 Neo4j（应急 / 无安装环境用）

给"没装 Neo4j 又想跑通导入"的机器准备的启动器。用的是官方 `neo4j-harness`，
起来的是**真实的 Neo4j 5.26 内核**：同一个 `bolt://` 协议、同一套 Cypher、同样的约束与索引，
`scripts/import_graph.py`、`scripts/build_graph.py` 和 Flask 应用都不需要改一行。

## 什么时候用

- 组员本机没装 Neo4j，只想验证导入/接口是否通；
- 答辩机不让装服务、也不让装 Docker；
- 想在 CI 里跑一遍导入，不想拉一个数据库服务。

**正式部署请仍用官网的 Neo4j Community 安装包**，见 `deploy/README.md`。本目录只是应急手段，
不是交付形态。

## 前置

- JDK 17（Neo4j 5.26 要求）
- Maven 3.6+

## 启动

```bash
cd dev/neo4j-embed
mvn -q compile exec:java
```

起来后：

| 端口 | 用途 |
|---|---|
| `bolt://127.0.0.1:7687` | 应用与导入脚本连接 |
| `http://127.0.0.1:7474` | HTTP 事务端点（**没有 Neo4j Browser 界面**） |

认证是关的，`.env` 里 `NEO4J_PASSWORD` 随便填一个非空值（脚本只检查它非空）。
换端口：`mvn -q compile exec:java -Dexec.args="target/neo4j-home 7688 7475"`。

数据落在 `dev/neo4j-embed/target/neo4j-home/data`（已 gitignore），**重启复用，不会丢**。
想清空重来：停掉进程后删掉 `target/neo4j-home/data` 再启动——`import_graph.py` 是幂等的，
但只有删目录能把约束也一起清掉。

> 目录里那些 32 位十六进制名的子目录（如 `d56e5852...`）是 harness 每次启动新建的临时
> 工作目录，只放日志和配置，几十 KB。之所以要把 `data_directory` 显式钉死，是因为
> harness 默认把数据也建在随机子目录里，重启即空库。攒多了可以随手删掉。

## 用它跑一遍导入

```bash
python scripts/build_graph.py       # 建结构 + 导入 + 对账
```

预期结尾：

```
[check] 全部一致
```

## 已知限制

- **没有 Browser 界面**：`http://127.0.0.1:7474/browser` 是 404。要看图请起 Flask 应用
  （`MOCK_DATA=0`）走页面，或直接用 Python 驱动跑 Cypher。
- **不是服务**：进程退出即关闭，没有守护进程；数据目录固定，重启后数据仍在。
  别拿它当常驻服务，正式环境请用安装包。
- **内存**：默认按机器内存自动分配，一般够 179 人 / 333 边这个量级；如果机器特别小，
  在 `EmbedServer.java` 里加 `.withConfig(GraphDatabaseSettings.pagecache_memory, "128M")`。

## 踩坑

### 1. `Non-parseable settings .../conf/settings.xml`

Maven 全局配置被改坏（常见于手动加镜像却没写 `</mirrors>` 闭合标签）。本机那份已修好
（备份 `settings.xml.bak-20261126`），别的机器遇到时，要么照第 3 节把镜像配置补对，
要么用一份空配置临时绕开：

```bash
echo '<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0"></settings>' > /tmp/g.xml
mvn -gs /tmp/g.xml -q compile exec:java
```

顺手把 `D:\Maven\...\conf\settings.xml` 修好，否则本机所有 Maven 项目都会报同一个错。

### 2. 依赖下载慢

配置阿里云镜像（`~/.m2/settings.xml`）：

```xml
<settings>
  <mirrors>
    <mirror>
      <id>aliyun</id>
      <url>https://maven.aliyun.com/repository/public</url>
      <mirrorOf>central</mirrorOf>
    </mirror>
  </mirrors>
</settings>
```

### 3. 端口占用

`7687` 被别的 Neo4j 占着时，改用 `-Dexec.args="target/neo4j-home 7688 7475"`，
同时把 `.env` 的 `NEO4J_URI` 改成 `bolt://127.0.0.1:7688`。
