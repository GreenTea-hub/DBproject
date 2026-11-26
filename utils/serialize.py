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


def node_to_dict(node):
    """Neo4j Node -> 前端节点。id 用业务标识（人物名），不用数据库内部编号。"""
    props = dict(node)
    name = props.get("name", "")
    faction = props.get("faction", "群雄")
    return {
        "id": name,
        "label": name,
        "category": faction,
        "value": int(props.get("value", 0) or 0),
        "role": props.get("role", ""),
        "aliases": props.get("aliases", []),
    }


def rel_to_dict(rel, source_name, target_name, direction="out"):
    props = dict(rel)
    if direction == "in":
        source_name, target_name = target_name, source_name
    return {
        "source": source_name,
        "target": target_name,
        "label": props.get("type", ""),
        "value": int(props.get("weight", 1) or 1),
        "evidence": props.get("evidence", ""),
        "confidence": float(props.get("confidence", 1.0) or 1.0),
    }


def graph_payload(nodes, links, categories=None):
    """统一出图结构：nodes / links / categories。"""
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
    props = dict(node)
    aliases = props.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [a for a in aliases.replace("，", "|").split("|") if a]
    return {
        "name": props.get("name", ""),
        "aliases": list(aliases),
        "faction": props.get("faction", ""),
        "role": props.get("role", ""),
        "gender": props.get("gender", ""),
        "birth_year": props.get("birth_year"),
        "death_year": props.get("death_year"),
    }
