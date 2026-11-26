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

数据落在 `dev/neo4j-embed/target/neo4j-home`（已 gitignore）。**想清空重来，停掉进程后删掉这个目录**——
`import_graph.py` 是幂等的，但删掉目录是唯一能把约束也一起清掉的办法。

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
- **不是服务**：进程退出数据就关闭，重启会复用同一目录。别拿它当常驻服务。
- **内存**：默认按机器内存自动分配，一般够 179 人 / 333 边这个量级；如果机器特别小，
  在 `EmbedServer.java` 里加 `.withConfig(GraphDatabaseSettings.pagecache_memory, "128M")`。

## 踩坑

### 1. `Non-parseable settings .../conf/settings.xml`

本机 Maven 的全局配置文件坏了（常见于手动改过镜像却没写闭合标签）。用一份空配置绕开：

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
