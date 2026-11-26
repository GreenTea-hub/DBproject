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
