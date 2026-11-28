"""图数据 -> 字典 / 图表结构。负责人：P3。

所有出图接口必须调用 graph_payload()，禁止各自手工拼 nodes / links。
出图结构见 docs/api.md 第 4 节。
"""

FACTION_COLORS = {
    "魏": "#1f6fd0",
    "蜀": "#c0392b",
    "吴": "#1e8e5a",
    "群雄": "#7f8c8d",
}


def _props(entity):
    """把节点/关系/属性字典统一成普通字典。

    neo4j 5.x 的 Node、Relationship 都实现了 Mapping，走 items() 取属性；
    查询里也可以用 properties(n) 直接拿字典。两种形态这里都能吃。
    Record.data() 会把关系变量压成元组，那是取不到属性的，直接报错提示改查询。
    """
    if isinstance(entity, dict):
        return entity
    items = getattr(entity, "items", None)
    if callable(items):
        return dict(items())
    raise TypeError(
        f"无法读取属性：{type(entity).__name__}。"
        "Cypher 里请用 properties(r) 取关系属性，不要直接 RETURN 关系变量"
    )


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value, default=1.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _alias_list(value):
    """别名统一成列表：兼容 Neo4j 的字符串数组与早期用 | 分隔的字符串。"""
    if not value:
        return []
    if isinstance(value, str):
        text = value.replace("，", "|").replace(",", "|").replace("、", "|")
        return [a for a in text.split("|") if a]
    return list(value)


def node_to_dict(node):
    """Neo4j Node -> 前端节点。id 用业务标识（人物名），不用数据库内部编号。"""
    props = _props(node)
    name = props.get("name", "")
    faction = props.get("faction") or "群雄"
    return {
        "id": name,
        "label": name,
        "category": faction,
        "value": _as_int(props.get("value", 0), 0),
        "role": props.get("role", ""),
        "aliases": _alias_list(props.get("aliases")),
    }


def rel_to_dict(rel, source_name, target_name, direction="out"):
    props = _props(rel)
    if direction == "in":
        source_name, target_name = target_name, source_name
    return {
        "source": source_name,
        "target": target_name,
        "label": props.get("type", ""),
        "value": _as_int(props.get("weight", 1), 1) or 1,
        "evidence": props.get("evidence", ""),
        "confidence": _as_float(props.get("confidence", 1.0), 1.0),
    }


def graph_payload(nodes, links, categories=None):
    """统一出图结构：nodes / links / categories。

    node.value 统一按“子图内关系数（度）”补全，前端用它控制节点大小。
    查询层没有返回 value 时，不能留 0——否则所有节点会被画成同样大小，
    文档示例里的 value=12 也就无从谈起。已有 value 的节点保持原值。
    """
    degrees = {}
    for link in links:
        degrees[link.get("source")] = degrees.get(link.get("source"), 0) + 1
        degrees[link.get("target")] = degrees.get(link.get("target"), 0) + 1
    for node in nodes:
        if not node.get("value"):
            node["value"] = degrees.get(node.get("id"), 0) or 1

    if categories is None:
        seen = []
        for node in nodes:
            cat = node.get("category", "群雄")
            if cat not in seen:
                seen.append(cat)
        categories = [{"name": c} for c in seen]
    return {"nodes": nodes, "links": links, "categories": categories}


def person_to_dict(node):
    """人物详情：属性平铺，别名转列表。"""
    props = _props(node)
    return {
        "name": props.get("name", ""),
        "aliases": _alias_list(props.get("aliases")),
        "faction": props.get("faction", ""),
        "role": props.get("role", ""),
        "gender": props.get("gender", ""),
        "birth_year": props.get("birth_year"),
        "death_year": props.get("death_year"),
    }
