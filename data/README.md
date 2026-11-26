# data 目录说明（负责人：P1）

## 1. 目录约定

| 目录 | 是否进仓库 | 内容 |
|---|---|---|
| `data/persons.csv` | 是 | 人物词典（179 人） |
| `data/factions.csv` | 是 | 阵营与配色（魏蓝、蜀红、吴绿、群雄灰） |
| `data/relations.csv` | 是 | 人物关系边（333 条，含证据与置信度） |
| `data/events.csv` | 是 | 关键事件表（83 条） |
| `data/raw/` | **否** | 一百二十回原文、切分后的章节文本 |
| `data/build/` | **否** | 中间产物（共现统计、章节清单等） |

`data/raw` 与 `data/build` 已写入 `.gitignore`，由 P1 统一放群共享目录，仓库里只保留
脚本与最终 CSV，保证任何人克隆仓库后按部署手册能重新生成。

生成流程（顺序不能乱）：

```
data/raw/sanguo_full.txt
  → python scripts/split_chapters.py      # 切 120 回，产出 data/raw/chapters/
  → python scripts/extract_mentions.py    # 统计共现，产出 data/build/cooccurrence.csv
  → 人工标注 relations.csv / events.csv
  → python scripts/extract_mentions.py --validate     # 格式质检
  → python scripts/check_data_quality.py              # 证据回原文核对
```

## 2. 列定义（第 9 周定死，改动需走 7.5 节契约变更流程）

### persons.csv
| 列 | 说明 |
|---|---|
| name | 人物主名，**唯一**，与 Neo4j `Person.name` 一致 |
| aliases | 别名，用竖线 `|` 分隔（字、号、官职、谥号），不要用逗号；无别名留空 |
| faction | 魏 / 蜀 / 吴 / 群雄（中文枚举，前端直接复用做配色） |
| role | 君主 / 武将 / 谋士 / 文臣 / 女子 / 其他 |
| gender | 男 / 女 |
| birth_year | 公元年份整数，未知留空 |
| death_year | 公元年份整数，未知留空 |

### relations.csv
| 列 | 说明 |
|---|---|
| source | 起点人物名，必须能在 persons.csv 中找到 |
| target | 终点人物名，同上 |
| type | 君臣 / 兄弟 / 敌对 / 亲族 / 师徒 / 同僚 |
| weight | 1—100 的整数，关系强度（见下方「权重口径」） |
| evidence | `第X回 回目名`，可加括号补充；脚本会把回目号与回目名回原文核对 |
| confidence | 0—1 的小数，标注置信度（判定标准见 `docs/data.md`） |

**去重约定**：同一对人只保留一条边，按 `source < target`（Unicode 顺序）书写，
导入脚本据此去重；`RELATED_TO` 查询时按无向处理。

**权重口径**：`weight` 表达"这层关系在小说里的分量"，不是纯词频。取值 =
共现强度（占七成，来自 `cooccurrence.csv`）+ 关系类型的结构性加成（君臣、亲族、
兄弟即便同回出场少也重），因此与纯共现排序不等价（Spearman ρ≈0.54），这是有意的。

**证据的三种形态**（P2 导入时会看到，务必区分）：

| evidence 结尾 | 含义 | 占比 |
|---|---|---|
| `（…）` 具体情节 | 人工读原文标注，可逐条核对 | 51% |
| `（首次出场，按阵营归属推定）` | 该人首次出场回目 + 阵营归属推出的君臣边，置信度 0.6 | 21% |
| `（同阵营共现 N 回）` | 同阵营且共现 ≥14 回，补的同僚边，置信度 0.66 | 26% |

### events.csv
| 列 | 说明 |
|---|---|
| name | 事件名，唯一 |
| year | 公元年份 |
| chapter | 回目号 1—120 |
| result | 事件结果一句话 |
| place | 发生地点（对应 Place 节点） |
| participants | 参与人物，格式 `人物:角色|人物:角色`，如 `刘备:主谋|关羽:参战` |

`participants` 里的角色词表共 36 个（前端做图例时直接用这个集合）：
主谋 / 参与 / 参战 / 献策 / 求助 / 救援 / 收留 / 收纳 / 斡旋 / 拥立 / 受托 / 主治 /
投奔 / 受让 / 受牵连 / 反对 / 拒绝 / 对峙 / 继位 / 继志 / 随军 /
受害 / 被围 / 被擒 / 被斩 / 被杀 / 被害 / 被放 / 被离间 / 败 / 死亡 / 战死 / 殉难 / 归降 / 投降 / 放行

### factions.csv
`name,color`，color 用十六进制，前端 `static/js/graph.js` 里的默认配色与此保持一致。

## 3. 质检要求

1. **格式**：`python scripts/extract_mentions.py --validate` 检查列名、枚举、外键、
   重复边、自环、孤立点；
2. **证据**：`python scripts/check_data_quality.py` 把每条 evidence 的回目号、回目名、
   双方是否在该回出场逐一回原文核对（当前 333 条全过）；
3. **抽样**：随机抽 10% 的边人工读原文复核情节描述是否准确（结论见 `docs/data.md`）；
4. **别名误配**：长名优先匹配（"刘玄德"不会被"刘备"截断，也不会被单字"刘"抢先），
   发现误配记入已知问题清单。

质检结果写进 `docs/data.md`，答辩时这段是必答内容。
