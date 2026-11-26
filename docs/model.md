# 图模型说明（负责人：P2，模型有变动时更新）

## 1. 为什么用图数据库

三国人物关系天然是网络：君臣、兄弟、敌对本身就是边，"刘备到曹操隔着几个人"在
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

## 3. 关系

| 关系 | 起点 → 终点 | 属性 | 说明 |
|---|---|---|---|
| RELATED_TO | Person → Person | type、weight、evidence、confidence | type 取君臣/兄弟/敌对/亲族/师徒/同僚；weight 1—100 |
| PARTICIPATED_IN | Person → Event | role | 人物参与事件 |
| BELONGS_TO | Person → Faction | — | 人物所属阵营（同时冗余 `Person.faction` 便于过滤） |
| APPEARS_IN | Person → Chapter | count | 人物在各回出现次数 |
| OCCURRED_AT | Event → Place | — | 事件发生地点 |
| IN_CHAPTER | Event → Chapter | — | 事件所属回目 |

**方向约定**：`RELATED_TO` 存储时有方向（导入时按 `source < target` 去重），
查询与展示时按无向处理——Cypher 中不写箭头即为双向匹配，避免 A→B 与 B→A 被当成两条无关边。

## 4. 约束与索引

见 `graph/schema.cypher`，全部使用 `IF NOT EXISTS`，可重复执行：

- 5 条唯一约束：Person.name、Faction.name、Event.name、Place.name、Chapter.no
- 2 条索引：Person.faction、Event.year

## 5. 设计取舍（答辩常问）
| 问题 | 回答要点 |
|---|---|
| 为什么给人物名建唯一约束？ | 导入用 MERGE，唯一约束既防重复又让 MERGE 走索引，批量导入快一个量级 |
| 为什么关系要存 type 属性而不是拆成 5 种关系类型？ | 前端配色与筛选都按 type 过滤，单类型便于一次查询拿到全部一跳邻居；代价是过滤要靠属性索引 |
| 为什么事件、回目单独建节点？ | 事件是"人物—事件"二部图的核心，回目支撑时间线与 APPEARS_IN 统计 |
| 出现次数怎么统计？ | 由 P1 的抽取脚本按回计数，导入时写进 APPEARS_IN.count |
| 合并重复人物怎么做？ | 别名并入保留者、关系迁移后 DETACH DELETE 多余节点，见 `queries_admin.merge_persons` |

## 6. 导入与核对（`scripts/import_graph.py`）

**导入顺序**：约束索引 → Faction → Chapter → Person → RELATED_TO → Event/Place → APPEARS_IN。
Chapter 必须早于 Event：事件只覆盖 83 回中的 70 回，若靠事件"顺带"建回目，另外 50 回
不会存在，且回目名只能写成空串（时间线页面会显示成"第 X 回"后面空着）。

**幂等**：全部用 `MERGE` + `SET`，同一份 CSV 连跑三次，节点与关系计数不变。
唯一约束让 `MERGE` 走索引，179 人 / 333 条边全量导入约 1 秒。

**参与者用 `MATCH` 不用 `MERGE`**：事件里的参与者若不在词典中，`MERGE` 会悄悄建出一个
没有阵营、没有关系的"幽灵人物"，图上表现为一个孤立小点，且 `--validate` 也发现不了
（它查的是 CSV，不是库）。现在导入前先在 Python 侧核对人名，命中词典外的直接报错退出，
并打印是哪条事件的哪个人。

**导入后自动对账**：`--check` 会拿库里的实际计数对比 CSV 行数（Person / Faction / Chapter /
Event / RELATED_TO / APPEARS_IN），再跑 6 项健康度检查——孤立人物、无阵营人物、
无参与人的事件、无地点的事件、既无事件也无人物的回、标题为空的回。任何一项不为 0
（"标题为空的回"除外）都以退出码 1 结束，`build_graph.py` 会因此中断，避免"导完了但数据是错的"。

实测（2026-11-26，空库重建）：

| 计数 | 实际 | 期望 |
|---|---|---|
| Person | 179 | 179 |
| Faction | 4 | 4 |
| Chapter | 120 | 120 |
| Event | 83 | 83 |
| Place | 51 | — |
| RELATED_TO | 333 | 333 |
| BELONGS_TO | 179 | — |
| PARTICIPATED_IN | 208 | — |
| OCCURRED_AT / IN_CHAPTER | 83 / 83 | — |
| APPEARS_IN | 2552 | 2552 |

健康度 6 项全部为 0。此后 `MOCK_DATA=0` 起服务，冒烟 9/9 通过，
`/api/persons?q=玄德` 命中刘备（别名检索）、`/api/timeline/刘备` 返回 19 条生平事件。
