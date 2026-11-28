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

    # Neo4j 的 list slice 下标是 32 位有符号数（上限 2,147,483,647），
    # page 极大时 (page-1)*size 会让 Cypher 抛 “Expected an integer
    # between -2147483648 and 2147483647”（500）。Cypher 里还要算
    # $skip + $size，所以上限再减去 size；夹住后自然返回空页，
    # 语义仍是“页码超出数据范围”，不会把异常暴露给前端。
    skip = min((page - 1) * size, 2**31 - 1 - size)
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
        data["relation_count"] = len(mock.relations(person["name"]) or [])
        data["chapter_count"] = mock.chapter_count(person["name"])
        return data

    # chapter_count 是"出场回目数"，用 count(DISTINCT a) 数关系条数；
    # 若用 sum(a.count) 得到的是提及总次数（刘备 2307），与字段名和页面文案对不上。
    cypher = """
    MATCH (p:Person {name: $name})
    OPTIONAL MATCH (p)-[r:RELATED_TO]-(:Person)
    WITH p, count(r) AS relation_count
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
    """人物的一跳关系列表。人物不存在返回 None，由接口层转成 404。"""
    if _use_mock():
        return mock.relations(name)

    # 这里显式用 properties(r) 摊平关系属性，并用 startNode/endNode 取端点；
    # 不依赖驱动对 Relationship 的默认转换，换 neo4j 版本也不会丢属性。
    #
    # 用 OPTIONAL MATCH 保证“人物存在但没有任何关系”也能返回一行空列表，
    # 从而和“人物不存在（零行）”区分开：前者 200 + items=[]，后者 404。
    cypher = """
    MATCH (p:Person {name: $name})
    OPTIONAL MATCH (p)-[r:RELATED_TO]-(o:Person)
    WITH p, r
    ORDER BY coalesce(r.weight, 0) DESC
    RETURN p.name AS name,
           collect(CASE WHEN r IS NULL THEN null ELSE {
               source: startNode(r).name,
               target: endNode(r).name,
               props: properties(r)
           } END) AS items
    """
    rows = run_query(cypher, name=name)
    if not rows:
        return None

    result = []
    for row in rows[0]["items"]:
        if row is None:
            continue
        result.append(rel_to_dict(row["props"], row["source"], row["target"]))
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

    # 类型过滤必须放进路径匹配，而不是查完再删 links：
    # 否则“只经由敌对边才连到的人”会作为孤立节点混进 nodes，出图结果与
    # types 参数语义不符。$types 是参数，不参与字符串拼接，无注入风险。
    type_filter = ""
    if types:
        type_filter = "WHERE all(rel IN relationships(path) WHERE rel.type IN $types)"

    cypher = f"""
    MATCH (center:Person {{name: $name}})
    OPTIONAL MATCH path = (center)-[:RELATED_TO*1..{depth}]-(n:Person)
    {type_filter}
    WITH center, collect(DISTINCT n) AS neighbors, collect(DISTINCT path) AS paths
    WITH [center] + [x IN neighbors WHERE x IS NOT NULL AND x <> center] AS ns,
         reduce(acc = [], ph IN paths |
                acc + CASE WHEN ph IS NULL THEN [] ELSE relationships(ph) END) AS all_rels
    UNWIND (CASE WHEN size(all_rels) = 0 THEN [null] ELSE all_rels END) AS r
    WITH ns, collect(DISTINCT r) AS rels
    RETURN [n IN ns | n] AS nodes,
           [r IN rels WHERE r IS NOT NULL | {{
               source: startNode(r).name,
               target: endNode(r).name,
               type: r.type,
               weight: r.weight
           }}] AS links
    """
    rows = run_query(cypher, name=name, types=types)
    if not rows:
        return None

    nodes = [node_to_dict(n) for n in rows[0]["nodes"]]
    links = []
    seen = set()
    for link in rows[0]["links"]:
        rel_type = link["type"] or ""
        if types and rel_type not in types:
            continue
        key = (link["source"], link["target"], rel_type)
        if key in seen:
            continue
        seen.add(key)
        try:
            weight = int(link["weight"] or 1)
        except (TypeError, ValueError):
            weight = 1
        links.append({
            "source": link["source"],
            "target": link["target"],
            "label": rel_type,
            "value": weight,
        })
    return graph_payload(nodes, links)


class _FakeNode(dict):
    """把 mock 的 dict 转成 serialize.person_to_dict 可处理的对象。"""

    def __init__(self, data):
        super().__init__(data)
