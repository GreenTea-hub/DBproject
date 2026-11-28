"""最短路、影响力排名、社区发现、小世界验证。负责人：P4。

weight 是关系强度，越大越近，不能沿路径相加。
加权模式选择最弱环节仍然最强的那条链，cost 就是这个最弱环节的强度。
跳数模式仍用 Cypher shortestPath，cost 等于跳数。
"""

from graph import mock
from graph.algo_fallback import (
    label_propagation,
    pagerank as pagerank_scores,
    small_world as small_world_metrics,
    widest_path,
)
from graph.driver import run_query
from utils.serialize import graph_payload

try:
    from flask import current_app
except ImportError:  # pragma: no cover
    current_app = None

HOP_LIMIT = 6
DAMPING = 0.85
ITERATIONS = 20


def _use_mock():
    if current_app is None:
        return False
    return bool(current_app.config.get("MOCK_DATA"))


def shortest_path(source, target, mode="shortest"):
    if _use_mock():
        return mock.shortest_path(source, target, mode)

    resolved = _resolve_pair(source, target)
    if resolved.get("missing") or resolved.get("ambiguous"):
        return {"nodes": [], "length": -1, "mode": mode, **resolved}
    source, target = resolved["source"], resolved["target"]
    if source == target:
        return _pack(source, target, mode, [source], [], 0, "identity")

    if mode == "weighted":
        return _weighted(source, target)
    return _unweighted(source, target)


def pagerank(limit=10):
    if _use_mock():
        return {"items": mock.pagerank(limit), "algorithm": "mock"}

    people = _people()
    factions = {row["name"]: row["faction"] or "群雄" for row in people}
    algorithm = "degree-centrality"
    scores = None
    if _gds_up():
        try:
            scores = _gds_pagerank()
            algorithm = "gds.pageRank"
        except Exception:
            scores = None
    if scores is None:
        scores = _degree_scores()
    for name in factions:
        scores.setdefault(name, 0.0)
    ordered = sorted(scores, key=lambda name: (-scores[name], name))
    items = [
        {
            "rank": index,
            "name": name,
            "faction": factions.get(name, "群雄"),
            "score": round(float(scores[name]), 6),
        }
        for index, name in enumerate(ordered[:limit], start=1)
    ]
    return {"items": items, "total": len(ordered), "algorithm": algorithm}


def communities():
    if _use_mock():
        return {"items": mock.communities(), "algorithm": "mock"}

    people = _people()
    factions = {row["name"]: row["faction"] or "群雄" for row in people}
    edges = _edges()
    algorithm = "label-propagation"
    assignments = None
    if _gds_up():
        try:
            assignments = _gds_louvain()
            algorithm = "gds.louvain"
        except Exception:
            assignments = None
    if assignments is None:
        names = list(factions)
        tuples = [(edge["source"], edge["target"], edge["weight"]) for edge in edges]
        assignments = label_propagation(names, tuples)
    items, agreement = _summarize(assignments, factions)
    return {"items": items, "total": len(items), "algorithm": algorithm, "agreement": agreement}


def small_world(sample=50):
    if _use_mock():
        return mock.small_world(sample) if hasattr(mock, "small_world") else {
            "avg_path": 2.17, "clustering": 0.31, "sample": sample, "mocked": True,
        }
    people = _people()
    edges = _edges()
    names = [row["name"] for row in people]
    tuples = [(edge["source"], edge["target"], edge["weight"]) for edge in edges]
    raw = small_world_metrics(names, tuples, sample=sample)
    return {
        "avg_path": _num(raw["avg_path_length"]),
        "clustering": _num(raw["avg_clustering"]),
        "sample": raw["sample"],
        "nodes": raw["nodes"],
        "edges": raw["edges"],
        "clustering_ratio": _num(raw["clustering_ratio"]),
        "path_ratio": _num(raw["path_ratio"]),
        "small_world_index": _num(raw["small_world_index"]),
        "algorithm": "python-smallworld",
    }


def _unweighted(source, target):
    rows = run_query(
        f"""
        MATCH (a:Person {{name: $source}}), (b:Person {{name: $target}})
        MATCH path = shortestPath((a)-[:RELATED_TO*..{HOP_LIMIT}]-(b))
        WITH nodes(path) AS ns, relationships(path) AS rs, length(path) AS length
        RETURN [n IN ns | n.name] AS nodes,
               [n IN ns | n.faction] AS factions,
               length,
               [i IN range(0, size(rs) - 1) | {{
                   source: ns[i].name,
                   target: ns[i + 1].name,
                   type: rs[i].type,
                   weight: rs[i].weight
               }}] AS relations
        """,
        **{"source": source, "target": target},
    )
    if not rows:
        return {"nodes": [], "length": -1, "mode": "shortest", "cost": None}
    row = rows[0]
    relations = _clean_relations(row["relations"])
    return _pack(source, target, "shortest", row["nodes"], relations, row["length"], "cypher.shortestPath", row["factions"])


def _weighted(source, target):
    people = _people()
    factions = {row["name"]: row["faction"] or "群雄" for row in people}
    edges = _edges()
    tuples = [(edge["source"], edge["target"], edge["weight"]) for edge in edges]
    path, bottleneck = widest_path(list(factions), tuples, source, target)
    if not path:
        return {"nodes": [], "length": -1, "mode": "weighted", "cost": None}
    relations = _relations_along(path, edges)
    return _pack(
        source, target, "weighted", path, relations, bottleneck, "widest-path",
        [factions.get(name, "群雄") for name in path],
    )


def _resolve_pair(source, target):
    found = {}
    for label in (source, target):
        if label in found:
            continue
        name = _resolve(label)
        if name is None:
            return {"missing": True}
        if isinstance(name, list):
            return {"ambiguous": True}
        found[label] = name
    return {"source": found[source], "target": found[target]}


def _resolve(label):
    rows = run_query(
        """
        MATCH (p:Person)
        WHERE p.name = $label OR $label IN coalesce(p.aliases, [])
        RETURN p.name AS name
        """,
        label=label,
    )
    exact = [row["name"] for row in rows if row["name"] == label]
    if exact:
        return exact[0]
    names = sorted({row["name"] for row in rows})
    if not names:
        return None
    if len(names) > 1:
        return names
    return names[0]


def _people():
    return run_query("MATCH (p:Person) RETURN p.name AS name, p.faction AS faction")


def _edges():
    return run_query(
        """
        MATCH (a:Person)-[r:RELATED_TO]->(b:Person)
        RETURN a.name AS source, b.name AS target, r.type AS type,
               coalesce(r.weight, 50) AS weight
        """
    )


def _gds_up():
    try:
        rows = run_query("RETURN gds.version() AS version")
    except Exception:
        return False
    return bool(rows and rows[0].get("version"))


def _gds_pagerank():
    _drop_topo()
    try:
        _project_topo()
        rows = run_query(
            """
            CALL gds.pageRank.stream('p4topo', {
              dampingFactor: $damping,
              maxIterations: $iterations
            })
            YIELD nodeId, score
            RETURN gds.util.asNode(nodeId).name AS name, score
            """,
            damping=DAMPING,
            iterations=ITERATIONS,
        )
    finally:
        _drop_topo()
    total = sum(row["score"] for row in rows) or 1.0
    return {row["name"]: row["score"] / total for row in rows}


def _gds_louvain():
    _drop_topo()
    try:
        _project_topo()
        rows = run_query(
            """
            CALL gds.louvain.stream('p4topo')
            YIELD nodeId, communityId
            RETURN gds.util.asNode(nodeId).name AS name, communityId AS community
            """
        )
    finally:
        _drop_topo()
    return {row["name"]: int(row["community"]) for row in rows}


def _project_topo():
    run_query(
        """
        CALL gds.graph.project(
          'p4topo',
          'Person',
          {RELATED_TO: {orientation: 'UNDIRECTED'}}
        )
        YIELD graphName
        RETURN graphName
        """
    )


def _drop_topo():
    try:
        run_query("CALL gds.graph.drop('p4topo', false) YIELD graphName RETURN graphName")
    except Exception:
        return


def _degree_scores():
    rows = run_query(
        """
        MATCH (p:Person)
        OPTIONAL MATCH (p)-[r:RELATED_TO]-()
        RETURN p.name AS name, count(r) AS score
        """
    )
    return {row["name"]: float(row["score"]) for row in rows}


def _relations_along(names, edges):
    best = {}
    for edge in edges:
        key = tuple(sorted((edge["source"], edge["target"])))
        current = best.get(key)
        if current is None or edge["weight"] > current["weight"]:
            best[key] = edge
    relations = []
    for left, right in zip(names, names[1:]):
        edge = best[tuple(sorted((left, right)))]
        relations.append({
            "source": left,
            "target": right,
            "type": edge.get("type") or "",
            "weight": int(edge["weight"]),
        })
    return relations


def _clean_relations(relations):
    cleaned = []
    for rel in relations or []:
        weight = rel.get("weight")
        cleaned.append({
            "source": rel["source"],
            "target": rel["target"],
            "type": rel.get("type") or "",
            "weight": int(weight) if weight is not None else 0,
        })
    return cleaned


def _pack(source, target, mode, names, relations, cost, algorithm, factions=None):
    factions = factions or []
    nodes = []
    for index, name in enumerate(names):
        faction = factions[index] if index < len(factions) and factions[index] else "群雄"
        nodes.append({"id": name, "label": name, "category": faction, "value": 1})
    links = [
        {
            "source": rel["source"],
            "target": rel["target"],
            "label": rel.get("type") or "",
            "value": int(rel.get("weight") or 1),
        }
        for rel in relations
    ]
    return {
        "from": source,
        "to": target,
        "nodes": names,
        "length": max(len(names) - 1, 0),
        "mode": mode,
        "cost": _num(cost),
        "relations": relations,
        "algorithm": algorithm,
        "graph": graph_payload(nodes, links),
    }


def _summarize(assignments, factions):
    order = ("魏", "蜀", "吴", "群雄")
    grouped = {}
    for name, community in assignments.items():
        grouped.setdefault(community, []).append(name)
    items = []
    same = 0
    total = 0
    for members in grouped.values():
        members = sorted(members)
        counts = {faction: 0 for faction in order}
        for member in members:
            faction = factions.get(member, "群雄")
            if faction not in counts:
                faction = "群雄"
            counts[faction] += 1
        majority = max(order, key=lambda faction: (counts[faction], -order.index(faction)))
        items.append({
            "size": len(members),
            "faction_majority": majority,
            "members": members,
        })
        total += len(members)
        same += sum(1 for member in members if factions.get(member, "群雄") == majority)
    items.sort(key=lambda item: (-item["size"], item["members"][0] if item["members"] else ""))
    for index, item in enumerate(items, start=1):
        item["community"] = index
    agreement = round(same / total, 4) if total else 0.0
    return items, agreement


def _num(value):
    if value is None:
        return None
    number = float(value)
    if number.is_integer():
        return int(number)
    return round(number, 4)
