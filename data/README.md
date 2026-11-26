# data 目录说明（负责人：P1）

## 1. 目录约定

| 目录 | 是否进仓库 | 内容 |
|---|---|---|
| `data/persons.csv` | 是 | 人物词典（最终产物，150—250 人） |
| `data/factions.csv` | 是 | 阵营与配色（魏蓝、蜀红、吴绿、群雄灰） |
| `data/relations.csv` | 是 | 人物关系边（含证据与置信度） |
| `data/events.csv` | 是 | 关键事件表（40 条以上） |
| `data/raw/` | **否** | 一百二十回原文、切分后的章节文本 |
| `data/build/` | **否** | 中间产物（共现统计、清洗日志等） |

`data/raw` 与 `data/build` 已写入 `.gitignore`，由 P1 统一放群共享目录，仓库里只保留
脚本与最终 CSV，保证任何人克隆仓库后按部署手册能重新生成。

## 2. 列定义（第 9 周定死，改动需走 7.5 节契约变更流程）

### persons.csv
| 列 | 说明 |
|---|---|
| name | 人物主名，**唯一**，与 Neo4j `Person.name` 一致 |
| aliases | 别名，用竖线 `|` 分隔（字、号、官职、谥号），不要用逗号 |
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
| weight | 1—100 的整数，归一化后的关系强度 |
| evidence | 原文依据，格式建议 `第X回 回目名`，可加一句原文 |
| confidence | 0—1 的小数，标注置信度 |

**去重约定**：同一对人只保留一条边，按 `source < target`（Unicode 顺序）书写，
导入脚本据此去重；`RELATED_TO` 查询时按无向处理。

### events.csv
| 列 | 说明 |
|---|---|
| name | 事件名，唯一 |
| year | 公元年份 |
| chapter | 回目号 1—120 |
| result | 事件结果一句话 |
| place | 发生地点（对应 Place 节点） |
| participants | 参与人物，格式 `人物:角色|人物:角色`，如 `刘备:主谋|关羽:参战` |

### factions.csv
`name,color`，color 用十六进制，前端 `static/js/graph.js` 里的默认配色与此保持一致。

## 3. 质检要求

1. 抽样核对：随机抽 10% 的关系边，回原文确认 `evidence` 真实存在；
2. 别名误配：长名优先匹配（"刘玄德"不能被"刘"抢先匹配），发现误配记入已知问题清单；
3. 孤立点：除刻意保留的冷门人物外，不应有度数为 0 的节点；
4. 校验脚本：`python scripts/extract_mentions.py --validate` 会检查列名、枚举、外键与重复边。

质检结果写进 `docs/data.md`，答辩时这段是必答内容。
