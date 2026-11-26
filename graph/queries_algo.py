"""最短路、影响力排名、社区发现、小世界验证。负责人：P4。

思路约定（写进算法文档时要能讲清）：
  最短路      —— shortest：Cypher shortestPath，按跳数；
                  weighted：把 weight 转成代价 cost = 101 - weight，用 Dijkstra（GDS 或 Python 兜底）；
  影响力排名  —— GDS PageRank，装不上 GDS 时退化为"度数中心性"近似，报告中如实说明；
  社区发现    —— GDS Louvain；
  小世界      —— 抽样计算平均最短路径与聚类系数。
"""

from flask import current_app

from graph import mock
from graph.driver import run_query


def _use_mock():
    return bool(current_app.config.get("MOCK_DATA"))


def shortest_path(source, target, mode="shortest"):
    if _use_mock():
        return mock.shortest_path(source, target, mode)

    if mode == "weighted":
        # TODO(P4)：GDS gds.shortestPath.dijkstra，关系权重用 cost = 101 - weight
        cypher = """
        MATCH (a:Person {name: $from}), (b:Person {name: $to})
        MATCH p = (a)-[:RELATED_TO*..6]-(b)
        WITH p, reduce(cost = 0, r IN relationships(p) | cost + (101 - coalesce(r.weight, 50))) AS total_cost
        ORDER BY total_cost ASC
        LIMIT 1
        RETURN [n IN nodes(p) | n.name] AS nodes, total_cost AS cost
        """
        rows = run_query(cypher, **{"from": source, "to": target})
        if not rows:
            return {"nodes": [], "length": -1, "mode": mode}
        return {"nodes": rows[0]["nodes"], "length": len(rows[0]["nodes"]) - 1,
                "cost": rows[0]["cost"], "mode": mode}

    cypher = """
    MATCH (a:Person {name: $from}), (b:Person {name: $to}),
          p = shortestPath((a)-[:RELATED_TO*..6]-(b))
    RETURN [n IN nodes(p) | n.name] AS nodes, length(p) AS length
    """
    rows = run_query(cypher, **{"from": source, "to": target})
    if not rows:
        return {"nodes": [], "length": -1, "mode": mode}
    return {"nodes": rows[0]["nodes"], "length": rows[0]["length"], "mode": mode}


def pagerank(limit=10):
    if _use_mock():
        return mock.pagerank(limit)

    # TODO(P4)：优先 GDS gds.pageRank.stream；以下为度数近似兜底
    cypher = """
    MATCH (p:Person)-[r:RELATED_TO]-()
    RETURN p.name AS name, count(r) AS score
    ORDER BY score DESC
    LIMIT $limit
    """
    rows = run_query(cypher, limit=limit)
    return [{"name": r["name"], "score": float(r["score"])} for r in rows]


def communities():
    if _use_mock():
        return mock.communities()

    # TODO(P4)：GDS gds.louvain.stream 投影 Person/RELATED_TO 后取 communityId
    cypher = """
    MATCH (p:Person)
    RETURN p.faction AS community, collect(p.name) AS members
    """
    rows = run_query(cypher)
    return [{"community": i, "members": r["members"]} for i, r in enumerate(rows, 1)]


def small_world(sample=50):
    """TODO(P4)：抽样计算平均最短路径与平均聚类系数，返回 {avg_path, clustering, sample}。"""
    if _use_mock():
        return {"avg_path": 2.17, "clustering": 0.31, "sample": sample, "mocked": True}
    return {"avg_path": None, "clustering": None, "sample": sample, "note": "待实现"}
