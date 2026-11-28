# 图模型说明（负责人：P2，模型有变动时更新）

## 1. 为什么用图数据库

三国人物关系天然是网络：君臣、兄弟、敌对本身就是边，“刘备到曹操隔着几个人”在
关系型数据库里要写递归 CTE 或多层自连接，在图库里是一行 `shortestPath`。
对比实验的实测数据见 `docs/algo.md`。

## 2. 节点

| 节点 | 属性 | 唯一约束 |
|---|---|---|
| Person | name、aliases、faction、role、gender、birth_year、death_year | name |
| Faction | name、color | name |
| Event | name、year、chapter、result | name |
| Place | name | name |
| Chapter | no、title | no |

两条容易踩的约定：

- `aliases` 存**字符串数组**（`["玄德","刘皇叔"]`），不存 `玄德|刘皇叔`。用分隔符字符串
  会导致“按别名搜索”退化成全文匹配，也没法建索引；
- `faction` 与 `BELONGS_TO` 是双写：前者给列表页过滤用，后者给图查询用。写接口在修改
  `faction` 时必须同步重建 `BELONGS_TO`，否则两处会不一致（`queries_admin.update_person` 已处理）。

## 3. 关系

| 关系 | 起点 → 终点 | 属性 | 说明 |
|---|---|---|---|
| RELATED_TO | Person → Person | type、weight、evidence、confidence | type 取君臣/兄弟/敌对/亲族/师徒/同僚；weight 1—100 |
| PARTICIPATED_IN | Person → Event | role | 人物参与事件 |
| BELONGS_TO | Person → Faction | — | 人物所属阵营（同时冗余 `Person.faction` 便于过滤） |
| APPEARS_IN | Person → Chapter | count | 人物在各回出现次数 |
| OCCURRED_AT | Event → Place | — | 事件发生地点 |
| IN_CHAPTER | Event → Chapter | — | 事件所属回目 |

### 方向与去重（答辩会问）

- **一对人物只保留一条 `RELATED_TO` 边**，关系类型是边上的 `type` 属性，不是五种独立关系。
- 写入时按人物名的 Unicode 顺序归一化：`source < target`。导入脚本
  （`scripts/import_graph.py`）与新增关系接口（`queries_admin.create_relation`）都执行这条规则。
- 查询与删除**一律按无向处理**（Cypher 里不写箭头）：`MATCH (a)-[r:RELATED_TO]-(b)`。
  存储方向只是为了实现“一对人一条边”，不代表语义方向。
- 代价：同一对人物不能同时表达“君臣”和“兄弟”（如刘备与关羽）。当前取舍是保留权重
  更高的那条，并在 `evidence` 里写清依据；这是后续可扩展成多边模型的点，答辩时如实说明。

## 4. 约束与索引

见 `graph/schema.cypher`，全部使用 `IF NOT EXISTS`，可重复执行：

- 5 条唯一约束：Person.name、Faction.name、Event.name、Place.name、Chapter.no
- 2 条索引：Person.faction、Event.year

| 对象 | 为什么需要 |
|---|---|
| Person.name 唯一 | 导入用 MERGE，唯一约束既防重，又让 MERGE 走索引；没有它，批量导入会退化成全表扫 |
| Faction/Event/Place/Chapter 唯一 | 同上，保证 MERGE 幂等，重复执行导入不会产生重复节点 |
| Person.faction 索引 | 列表页按阵营过滤、社区发现按阵营对照 |
| Event.year 索引 | 时间线按年份区间过滤 |

没有给 `RELATED_TO.type` 建索引：类型过滤总是先落在一跳邻居或子图内，候选集只有几十条边，
全表扫属性比维护索引更划算。数据量到十万级再考虑关系属性索引。

## 5. 导入流程与幂等

`python scripts/build_graph.py` 依次执行：建约束索引 → 导入节点 → 导入关系 → 数量核对。
`--reset` 会先清空全库，适合结构变更或脏数据回炉。

| 环节 | 做法 | 保证 |
|---|---|---|
| 节点 | `UNWIND $rows` + `MERGE`，每批 500 行 | 重复执行不产生重复节点 |
| 关系 | 先归一化方向、按 `(source,target)` 去重，再 `MERGE` | 一对人物只有一条边 |
| 事件参与者 | `OPTIONAL MATCH` 已存在的人物，匹配不到就跳过并告警 | 不会生成没有阵营的“影子人物” |
| 关系外键 | 导入前校验 source/target 在 persons.csv 中 | 不会产生指向不存在人物的边 |
| 枚举 | type 不在六种之内直接跳过并计数 | 脏数据不落库 |

去重规则：同一对人物出现多行时，保留 `weight` 最大的一行（`weight` 相同则保留先出现的）。
被合并的行数、缺失人物、非法类型、空行都会打印，导入结束必须核对以下九项：

```
Person / Faction / Event / Chapter / RELATED_TO / 孤立人物
反向关系边（应为 0）/ 缺阵营人物（应为 0）/ 无参与者事件
```

增量导入是幂等的；但历史库里若已经存在反向重复边，脚本不会自动改写方向，需 `--reset` 重建。

## 6. 增删改接口语义

| 操作 | 成功 | 失败 | 规则 |
|---|---|---|---|
| POST /api/persons | 201 | 400 / 409 | 已存在返回 409，不静默覆盖 |
| PUT /api/persons/<name> | 200 | 400 / 404 | 只改白名单字段；改 faction 同步 BELONGS_TO |
| DELETE /api/persons/<name> | 200 | 404 | `DETACH DELETE`，不留孤立边 |
| POST /api/relations | 201 | 400 / 404 / 409 | weight 1—100、confidence 0—1；两人须存在且之间无关系 |
| DELETE /api/relations | 200 | 400 / 404 | 按无向匹配，source/target 顺序无关 |
| POST /api/persons/merge | 200 | 400 / 404 | keep 与 drop 不能相同，两人都须存在 |

所有写操作都用参数化 Cypher；唯一允许拼接的是子图深度（白名单整数，见
`queries_person.person_subgraph`），写接口不涉及。

## 7. 合并重复人物

场景：“诸葛亮”与“孔明”被词典拆成两个节点。合并分四步，整条 Cypher 是一个事务
（`queries_admin.merge_persons`），不会留下“别名改了、关系没迁”的半成品：

| 步骤 | 处理 |
|---|---|
| 1. 别名 | `keep.aliases + drop.name + drop.aliases`，去重并保持顺序 |
| 2. RELATED_TO | 按无向迁移到 keep；与既有边同类型时取 weight / confidence 较大者、evidence 较长者 |
| 3. PARTICIPATED_IN | 迁移事件参与；keep 已有该事件则保留原角色 |
| 4. APPEARS_IN | 同一回目的 count 相加 |
| 5. BELONGS_TO | keep 已有阵营则保留，没有才继承 drop 的 |
| 6. 删除 | `DETACH DELETE drop`，此时 drop 已无业务关系 |

只迁 `RELATED_TO` 是不够的：`DETACH DELETE` 会连带删掉 `PARTICIPATED_IN`、`APPEARS_IN`、
`BELONGS_TO`，合并后的人物会凭空失去事件、回目统计和阵营，时间线与人物详情立刻出错。

> 占位数据说明：`MOCK_DATA=1` 时数据来自 `graph/mock.py`（P3 所有）。由于
> `mock.merge_persons` 会按别名查找、误删保留者，P2 在
> `queries_admin._mock_merge_persons` 里按上述规则重写了占位合并（别名去重、关系去重、
> 事件参与者替换）。接真库后两条路径行为一致。

## 8. 设计取舍（答辩常问）

| 问题 | 回答要点 |
|---|---|
| 为什么给人物名建唯一约束？ | 导入用 MERGE，唯一约束既防重复又让 MERGE 走索引，批量导入快一个量级 |
| 为什么关系要存 type 属性而不是拆成 5 种关系类型？ | 前端配色与筛选都按 type 过滤，单类型便于一次查询拿到全部一跳邻居；代价是过滤要靠属性索引 |
| 为什么不是拆成 5 种、也不是多边？ | 拆 5 种会让“取全部一跳邻居”变成 5 次查询；多边能表达“君臣+兄弟”，但去重与权重计算复杂。当前规模选一条边 + type 属性，是查询简洁与语义完整之间的折中 |
| 为什么事件、回目单独建节点？ | 事件是“人物—事件”二部图的核心，回目支撑时间线与 APPEARS_IN 统计 |
| 为什么存储有向、查询无向？ | 有向是为了让一对人物只有一条边、便于 MERGE 去重；无向是因为三国关系语义上双向（刘备与关羽既是君臣也是兄弟） |
| 出现次数怎么统计？ | 由 P1 的抽取脚本按回计数，导入时写进 APPEARS_IN.count |
| 合并重复人物怎么做？ | 别名并入保留者、迁移四类关系、最后 DETACH DELETE，见第 7 节 |
| 为什么导入不用 CREATE？ | CREATE 每次执行都会新增节点，重跑一次数据就翻倍；MERGE 依赖唯一约束才能既幂等又不全表扫 |

## 9. 已知限制

- `Event.year` 只精确到年份，同年事件只能靠 `chapter` 排先后；时间线不展示月日；
- 一对人物一条边，无法同时表达多种关系类型（见第 3 节）；
- 反向重复边不会被增量导入自动修复，需 `build_graph.py --reset`；
- 别名重合（“子龙”偶指他人）属于数据层问题，由 P1 的已知问题清单跟踪。
