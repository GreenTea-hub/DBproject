"""占位数据（Mock）。负责人：P3。

作用：Neo4j 还没入库时，P3/P4/P5 都能先按 7.2/7.4 的契约把接口和页面写完。
用法：.env 里 MOCK_DATA=1 即走这里；数据入库后改成 0，接口无缝切换。
禁止把这里的样例数据当作最终数据——真实数据由 P1 产出、P2 导入。
"""

from utils.serialize import graph_payload, node_to_dict, rel_to_dict

PERSONS = [
    {"name": "刘备", "aliases": ["玄德", "刘皇叔", "先主"], "faction": "蜀", "role": "君主", "gender": "男", "birth_year": 161, "death_year": 223},
    {"name": "关羽", "aliases": ["云长", "关公", "美髯公"], "faction": "蜀", "role": "武将", "gender": "男", "birth_year": 160, "death_year": 220},
    {"name": "张飞", "aliases": ["翼德", "张翼德"], "faction": "蜀", "role": "武将", "gender": "男", "birth_year": 167, "death_year": 221},
    {"name": "诸葛亮", "aliases": ["孔明", "卧龙", "武侯"], "faction": "蜀", "role": "谋士", "gender": "男", "birth_year": 181, "death_year": 234},
    {"name": "曹操", "aliases": ["孟德", "曹孟德", "魏武帝"], "faction": "魏", "role": "君主", "gender": "男", "birth_year": 155, "death_year": 220},
    {"name": "孙权", "aliases": ["仲谋", "吴大帝"], "faction": "吴", "role": "君主", "gender": "男", "birth_year": 182, "death_year": 252},
    {"name": "吕布", "aliases": ["奉先", "吕奉先"], "faction": "群雄", "role": "武将", "gender": "男", "birth_year": 161, "death_year": 199},
    {"name": "貂蝉", "aliases": ["闭月"], "faction": "群雄", "role": "女子", "gender": "女", "birth_year": None, "death_year": None},
]

RELATIONS = [
    {"source": "刘备", "target": "关羽", "type": "兄弟", "weight": 95, "evidence": "第一回 宴桃园豪杰三结义", "confidence": 0.98},
    {"source": "刘备", "target": "张飞", "type": "兄弟", "weight": 93, "evidence": "第一回 宴桃园豪杰三结义", "confidence": 0.98},
    {"source": "关羽", "target": "张飞", "type": "兄弟", "weight": 90, "evidence": "第一回 宴桃园豪杰三结义", "confidence": 0.95},
    {"source": "刘备", "target": "诸葛亮", "type": "君臣", "weight": 92, "evidence": "第三十八回 定三分隆中决策", "confidence": 0.96},
    {"source": "刘备", "target": "曹操", "type": "敌对", "weight": 88, "evidence": "第二十一回 曹操煮酒论英雄", "confidence": 0.9},
    {"source": "曹操", "target": "吕布", "type": "敌对", "weight": 84, "evidence": "第十九回 白门楼吕布殒命", "confidence": 0.92},
    {"source": "吕布", "target": "貂蝉", "type": "亲族", "weight": 70, "evidence": "第八回 王司徒巧使连环计", "confidence": 0.8},
    {"source": "刘备", "target": "孙权", "type": "敌对", "weight": 60, "evidence": "第八十四回 陆逊营烧七百里", "confidence": 0.75},
    {"source": "孙权", "target": "曹操", "type": "敌对", "weight": 78, "evidence": "第四十八回 宴长江曹操赋诗", "confidence": 0.85},
]

EVENTS = [
    {"name": "桃园结义", "year": 184, "chapter": 1, "result": "刘关张结为兄弟", "place": "涿郡", "participants": ["刘备", "关羽", "张飞"]},
    {"name": "煮酒论英雄", "year": 199, "chapter": 21, "result": "刘备借雷掩饰，得以脱身", "place": "许都", "participants": ["曹操", "刘备"]},
    {"name": "白门楼", "year": 199, "chapter": 19, "result": "吕布被曹操所杀", "place": "下邳", "participants": ["曹操", "刘备", "吕布"]},
    {"name": "隆中对", "year": 207, "chapter": 38, "result": "诸葛亮出山辅佐刘备", "place": "隆中", "participants": ["刘备", "诸葛亮"]},
]


def _find(name):
    for p in PERSONS:
        if p["name"] == name or name in p["aliases"]:
            return p
    return None


def search(q="", faction="", page=1, size=20):
    rows = PERSONS
    if faction:
        rows = [p for p in rows if p["faction"] == faction]
    if q:
        rows = [
            p for p in rows
            if q in p["name"] or any(q in a for a in p["aliases"])
        ]
    total = len(rows)
    start = (page - 1) * size
    return rows[start:start + size], total


def detail(name):
    return _find(name)


def relations(name):
    """人物的一跳关系。字段与真实接口保持一致（label / value），
    否则占位模式与接库模式的返回结构不同，前端和冒烟脚本会被骗过。"""
    return [
        {
            "source": r["source"],
            "target": r["target"],
            "label": r["type"],
            "value": r["weight"],
            "evidence": r.get("evidence", ""),
            "confidence": r.get("confidence", 1.0),
        }
        for r in RELATIONS
        if name in (r["source"], r["target"])
    ]


def subgraph(name, depth=1, types=None):
    """两层以内的小子图：直接用内存数据做广度扩展，仅用于占位。"""
    center = _find(name)
    if center is None:
        return None

    keep_types = set(types or [])
    nodes = {center["name"]: node_to_dict(_Node(center))}
    links = []
    frontier = [center["name"]]

    for _ in range(max(1, min(depth, 3))):
        next_frontier = []
        for current in frontier:
            for rel in relations(current):
                if keep_types and rel["label"] not in keep_types:
                    continue
                other_name = rel["target"] if rel["source"] == current else rel["source"]
                other = _find(other_name)
                if other is None:
                    continue
                if other_name not in nodes:
                    nodes[other_name] = node_to_dict(_Node(other))
                    next_frontier.append(other_name)
                links.append({
                    "source": rel["source"],
                    "target": rel["target"],
                    "label": rel["label"],
                    "value": rel["value"],
                })
        frontier = next_frontier
        if not frontier:
            break

    return graph_payload(list(nodes.values()), links)


class _Node(dict):
    """把 dict 包装成 serialize.node_to_dict 能吃的形状（模拟 Neo4j Node 的属性访问）。"""

    def __init__(self, data):
        super().__init__(data)
        self["value"] = 1


def pagerank(limit=10):
    rows = sorted(PERSONS, key=lambda p: len(relations(p["name"])), reverse=True)
    return [{"name": p["name"], "score": round(len(relations(p["name"])) / 10, 3)} for p in rows[:limit]]


def communities():
    groups = {}
    for p in PERSONS:
        groups.setdefault(p["faction"], []).append(p["name"])
    return [{"community": i, "members": members} for i, members in enumerate(groups.values(), 1)]


def shortest_path(source, target, mode="shortest"):
    if source == target:
        return {"nodes": [source], "length": 0}
    # 仅占位：真实实现由 P4 用 Cypher shortestPath 完成
    for rel in RELATIONS:
        pair = {rel["source"], rel["target"]}
        if pair == {source, target}:
            return {"nodes": [source, target], "length": 1, "mode": mode}
    return {"nodes": [], "length": -1, "mode": mode}


# ---------------------------------------------------------------- 写操作（仅占位用）
# 目的：让管理页与冒烟脚本在未接数据库时也能走通"写入 -> 查询 -> 删除"。

def create_person(name, aliases=None, faction="群雄", role="", gender="", birth_year=None, death_year=None):
    existing = _find(name)
    if existing is not None:
        existing.update({"aliases": aliases or [], "faction": faction, "role": role,
                         "gender": gender, "birth_year": birth_year, "death_year": death_year})
        return {"name": existing["name"], "updated": True, "mock": True}
    PERSONS.append({
        "name": name, "aliases": aliases or [], "faction": faction, "role": role,
        "gender": gender, "birth_year": birth_year, "death_year": death_year,
    })
    return {"name": name, "created": True, "mock": True}


def update_person(name, fields):
    person = _find(name)
    if person is None:
        return {"updated": 0, "mock": True}
    allowed = {"aliases", "faction", "role", "gender", "birth_year", "death_year"}
    for key, value in fields.items():
        if key in allowed:
            person[key] = value
    return {"name": person["name"], "updated": len(fields), "mock": True}


def delete_person(name):
    global PERSONS
    person = _find(name)
    if person is None:
        return {"deleted": 0, "mock": True}
    PERSONS = [p for p in PERSONS if p["name"] != person["name"]]
    RELATIONS[:] = [r for r in RELATIONS
                    if r["source"] != person["name"] and r["target"] != person["name"]]
    return {"name": person["name"], "deleted": 1, "mock": True}


def create_relation(source, target, rel_type, weight=50, evidence="", confidence=0.5):
    RELATIONS.append({"source": source, "target": target, "type": rel_type,
                      "weight": weight, "evidence": evidence, "confidence": confidence})
    return {"source": source, "target": target, "created": True, "mock": True}


def delete_relation(source, target, rel_type=None):
    before = len(RELATIONS)
    RELATIONS[:] = [r for r in RELATIONS if not (
        {r["source"], r["target"]} == {source, target}
        and (rel_type is None or r["type"] == rel_type)
    )]
    return {"deleted": before - len(RELATIONS), "mock": True}


def merge_persons(keep, drop):
    keep_person = _find(keep)
    drop_person = _find(drop)
    if keep_person is None or drop_person is None:
        return {"keep": keep, "drop": drop, "deleted": 0, "mock": True}
    keep_person["aliases"] = list(dict.fromkeys(
        keep_person["aliases"] + [drop_person["name"]] + drop_person["aliases"]
    ))
    for rel in RELATIONS:
        if rel["source"] == drop_person["name"]:
            rel["source"] = keep_person["name"]
        if rel["target"] == drop_person["name"]:
            rel["target"] = keep_person["name"]
    delete_person(drop_person["name"])
    return {"keep": keep_person["name"], "drop": drop, "merged": True, "mock": True}


__all__ = [
    "PERSONS", "RELATIONS", "EVENTS", "search", "detail",
    "relations", "subgraph", "pagerank", "communities", "shortest_path",
    "create_person", "update_person", "delete_person",
    "create_relation", "delete_relation", "merge_persons",
]
