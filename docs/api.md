# 接口文档（负责人：P3，接口有变动时更新）

> 三份约定（数据模型、响应格式、出图结构）第 9 周冻结；此后只允许新增字段，
> 不允许改名或删除。变更必须走分工方案 7.5 节流程。

## 1. 统一响应

成功：

```json
{ "code": 0, "data": { }, "message": "" }
```

列表分页：

```json
{ "code": 0, "data": { "items": [], "total": 123, "page": 1, "size": 20 }, "message": "" }
```

失败：HTTP 4xx/5xx，正文 `{"code": 400, "message": "人物不存在"}`。

> 前端只判断 `code === 0`，不要每个接口写一套解析逻辑（统一走 `static/js/common.js` 的 `apiGet`）。

## 2. 接口清单

| 方法 | 路径 | 提供者 | 说明 |
|---|---|---|---|
| GET | `/api/health` | P3 | 健康检查，返回 `{service, db, mock}` |
| GET | `/api/persons?q=&faction=&page=&size=` | P3 | 人物搜索与分页（q 同时匹配姓名与别名） |
| GET | `/api/persons/<name>` | P3 | 人物详情（含 relation_count、chapter_count） |
| GET | `/api/persons/<name>/graph?depth=&types=` | P3 | 人物子图，返回出图结构 |
| GET | `/api/persons/<name>/relations` | P3 | 一跳关系列表 |
| GET | `/api/events?year_from=&year_to=` | P2 | 事件列表 |
| GET | `/api/events/<name>` | P2 | 事件详情（含参与者与地点） |
| GET | `/api/timeline/<name>` | P2 | 人物生平时间线 |
| POST | `/api/persons` | P2 | 新增人物 |
| PUT | `/api/persons/<name>` | P2 | 修改人物（白名单字段） |
| DELETE | `/api/persons/<name>` | P2 | 删除人物（DETACH DELETE） |
| POST | `/api/relations` | P2 | 新增关系 |
| DELETE | `/api/relations` | P2 | 删除关系（JSON 体传 source/target/type） |
| POST | `/api/persons/merge` | P2 | 合并重复人物（keep / drop） |
| GET | `/api/path?from=&to=&mode=` | P4 | 最短路，mode=shortest / weighted |
| GET | `/api/stats/pagerank?limit=` | P4 | 影响力排名 |
| GET | `/api/stats/communities` | P4 | 阵营社区发现 |
| GET | `/api/stats/smallworld?sample=` | P4 | 小世界验证 |

## 3. 参数约束

| 参数 | 约束 | 越界处理 |
|---|---|---|
| page | ≥ 1 | 小于 1 时按 1 处理 |
| size | 1—100，默认 20 | 超过 100 截断为 100 |
| depth | 1—3，默认 1 | 截断到区间内 |
| types | 逗号分隔，取值限 君臣/兄弟/敌对/亲族/师徒/同僚 | 非法值忽略 |
| mode | shortest / weighted | 其余返回 400 |
| from / to | 必须是已存在的人物名 | 不存在返回 404「两人之间不存在路径」 |

## 4. 出图结构（所有画图接口必须一致）

```json
{
  "nodes": [{ "id": "刘备", "label": "刘备", "category": "蜀", "value": 12 }],
  "links": [{ "source": "刘备", "target": "关羽", "label": "兄弟", "value": 9 }],
  "categories": [{ "name": "魏" }, { "name": "蜀" }, { "name": "吴" }, { "name": "群雄" }]
}
```

- `id` 用人物名，不用数据库内部编号（重建库后编号会变，前端选中状态会错乱）；
- `category` 直接用中文阵营值，前端配色表 `static/js/graph.js` 与之对应。

## 5. 示例

```
GET /api/persons/%E5%88%98%E5%A4%87/graph?depth=2&types=%E5%85%84%E5%BC%9F
```

```json
{
  "code": 0,
  "data": {
    "nodes": [
      { "id": "刘备", "label": "刘备", "category": "蜀", "value": 1 },
      { "id": "关羽", "label": "关羽", "category": "蜀", "value": 1 }
    ],
    "links": [{ "source": "刘备", "target": "关羽", "label": "兄弟", "value": 95 }],
    "categories": [{ "name": "蜀" }]
  },
  "message": ""
}
```

## 6. 变更记录

| 日期 | 变更 | 提出人 | 影响接口 |
|---|---|---|---|
| 待填 | 初始冻结版本 v1.0 | P3 | 全部 |
