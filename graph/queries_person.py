"""人物、搜索、关系、子图查询。负责人：P3（文件归属 P3，其他人不要直接改）。"""

from flask import current_app

from graph import mock
from graph.driver import run_query
from utils.serialize import graph_payload, node_to_dict, person_to_dict, rel_to_dict


def _use_mock():
    return bool(current_app.config.get("MOCK_DATA"))


def search_persons(q="", faction="", page=1, size=20):
    """返回 (items, total)。q 同时匹配姓名与别名。"""
    if _use_mock():
        rows, total = mock.search(q, faction, page, size)
        return [person_to_dict(_FakeNode(r)) for r in rows], total

    skip = (page - 1) * size
    cypher = """
    MATCH (p:Person)
    WHERE ($q = '' OR p.name CONTAINS $q OR any(a IN coalesce(p.aliases, []) WHERE a CONTAINS $q))
      AND ($faction = '' OR p.faction = $faction)
    WITH p ORDER BY p.name
    RETURN collect(p)[$skip..$skip + $size] AS page_items, count(p) AS total
    """
    rows = run_query(cypher, q=q, faction=faction, skip=skip, size=size)
    if not rows:
        return [], 0
    page_items = rows[0]["page_items"]
    total = rows[0]["total"]
    return [person_to_dict(item) for item in page_items], total


def get_person(name):
    """人物详情，附关系数与出现回目数。不存在返回 None。"""
    if _use_mock():
        person = mock.detail(name)
        if person is None:
            return None
        data = dict(person)
        data["relation_count"] = len(mock.relations(person["name"]))
        data["chapter_count"] = 0
        return data

    # chapter_count 是"出场回目数"，用 count(DISTINCT a) 数关系条数；
    # 若用 sum(a.count) 得到的是提及总次数（刘备 2307），与字段名和页面文案对不上。
    cypher = """
    MATCH (p:Person {name: $name})
    OPTIONAL MATCH (p)-[:RELATED_TO]-(o:Person)
    WITH p, count(DISTINCT o) AS relation_count
    OPTIONAL MATCH (p)-[a:APPEARS_IN]->(:Chapter)
    RETURN p, relation_count, count(DISTINCT a) AS chapter_count
    """
    rows = run_query(cypher, name=name)
    if not rows:
        return None
    row = rows[0]
    data = person_to_dict(row["p"])
    data["relation_count"] = row["relation_count"]
    data["chapter_count"] = row["chapter_count"]
    return data


def list_relations(name):
    """人物的一跳关系列表。"""
    if _use_mock():
        return mock.relations(name)

    # 注意：这里必须用 properties(r) 取属性，不能直接 RETURN r。
    # run_query 走 Record.data()，而 neo4j 5.x 的 data() 会把关系变量压成
    # (起点属性, 类型, 终点属性) 三元组，接口层再 dict() 就会 500。
    cypher = """
    MATCH (p:Person {name: $name})-[r:RELATED_TO]-(o:Person)
    RETURN p.name AS source, o.name AS target, properties(r) AS props
    ORDER BY r.weight DESC
    """
    rows = run_query(cypher, name=name)
    result = []
    for row in rows:
        item = rel_to_dict(row["props"], row["source"], row["target"])
        result.append(item)
    return result


def person_subgraph(name, depth=1, types=None):
    """人物子图。depth 已在接口层限制为 1..3，这里仍再校验一次。

    Cypher 的变长路径不能把跳数写成参数（*$depth 非法），只能用 f-string
    拼一个经过白名单校验的整数，这是唯一安全的拼接点。
    """
    if _use_mock():
        return mock.subgraph(name, depth, types)

    depth = max(1, min(int(depth or 1), 3))
    types = types or []

    cypher = f"""
    MATCH (center:Person {{name: $name}})
    OPTIONAL MATCH path = (center)-[:RELATED_TO*1..{depth}]-(n:Person)
    WITH center, collect(DISTINCT n) + center AS ns, collect(DISTINCT path) AS paths
    WITH ns, [p IN paths WHERE p IS NOT NULL | relationships(p)] AS rel_lists
    WITH ns, reduce(acc = [], rl IN rel_lists | acc + rl) AS all_rels
    UNWIND (CASE WHEN size(all_rels) = 0 THEN [null] ELSE all_rels END) AS r
    WITH ns, collect(DISTINCT r) AS rels
    RETURN [n IN ns WHERE n IS NOT NULL | n] AS nodes,
           [r IN rels WHERE r IS NOT NULL | {{
               source: startNode(r).name,
               target: endNode(r).name,
               type: r.type,
               weight: r.weight
           }}] AS links
    """
    rows = run_query(cypher, name=name)
    if not rows:
        return None

    nodes = [node_to_dict(n) for n in rows[0]["nodes"]]
    links = []
    for link in rows[0]["links"]:
        if types and link["type"] not in types:
            continue
        links.append({
            "source": link["source"],
            "target": link["target"],
            "label": link["type"] or "",
            "value": link["weight"] or 1,
        })
    return graph_payload(nodes, links)


class _FakeNode(dict):
    """把 mock 的 dict 转成 serialize.person_to_dict 可处理的对象。"""

    def __init__(self, data):
        super().__init__(data)
