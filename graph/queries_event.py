"""事件、时间线、地点查询。负责人：P2。

接口契约见 docs/api.md：
  GET /api/events?year_from=&year_to=
  GET /api/events/<name>
  GET /api/timeline/<name>
"""

from flask import current_app

from graph import mock
from graph.driver import run_query


def _use_mock():
    return bool(current_app.config.get("MOCK_DATA"))


def list_events(year_from=None, year_to=None):
    if _use_mock():
        rows = mock.EVENTS
        if year_from is not None:
            rows = [e for e in rows if e["year"] >= year_from]
        if year_to is not None:
            rows = [e for e in rows if e["year"] <= year_to]
        return rows

    cypher = """
    MATCH (e:Event)
    WHERE ($year_from IS NULL OR e.year >= $year_from)
      AND ($year_to IS NULL OR e.year <= $year_to)
    OPTIONAL MATCH (e)-[:OCCURRED_AT]->(pl:Place)
    RETURN e.name AS name, e.year AS year, e.chapter AS chapter,
           e.result AS result, pl.name AS place
    ORDER BY e.year, e.chapter
    """
    return run_query(cypher, year_from=year_from, year_to=year_to)


def get_event(name):
    if _use_mock():
        for e in mock.EVENTS:
            if e["name"] == name:
                return dict(e)
        return None

    cypher = """
    MATCH (e:Event {name: $name})
    OPTIONAL MATCH (e)-[:OCCURRED_AT]->(pl:Place)
    OPTIONAL MATCH (p:Person)-[r:PARTICIPATED_IN]->(e)
    RETURN e, pl.name AS place,
           collect(CASE WHEN p IS NULL THEN null ELSE {name: p.name, role: r.role} END) AS participants
    """
    rows = run_query(cypher, name=name)
    if not rows:
        return None
    row = rows[0]
    data = dict(row["e"])
    data["place"] = row["place"]
    data["participants"] = [p for p in row["participants"] if p]
    return data


def timeline(name):
    """人物生平时间线：按年份排序的事件列表。TODO(P2)：补上同年内的回目次序。"""
    if _use_mock():
        rows = [e for e in mock.EVENTS if name in e.get("participants", [])]
        return [{"year": e["year"], "chapter": e["chapter"], "event": e["name"], "result": e["result"]} for e in rows]

    cypher = """
    MATCH (p:Person {name: $name})-[:PARTICIPATED_IN]->(e:Event)
    RETURN e.year AS year, e.chapter AS chapter, e.name AS event, e.result AS result
    ORDER BY e.year, e.chapter
    """
    return run_query(cypher, name=name)
