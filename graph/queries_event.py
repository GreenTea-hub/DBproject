"""事件、时间线、地点查询。负责人：P2。

接口契约见 docs/api.md：
  GET /api/events?year_from=&year_to=
  GET /api/events/<name>
  GET /api/timeline/<name>

排序约定：Event.year 只精确到公元年份，同年事件按回目号（chapter）排先后，
因此所有列表统一按 (year, chapter, name) 升序，年份缺失的排在最后。
"""

from flask import current_app

from graph import mock
from graph.driver import run_query


def _use_mock():
    return bool(current_app.config.get("MOCK_DATA"))


def _event_sort_key(row):
    """年份缺失的排最后；同年按回目，再按事件名，保证结果稳定。"""
    year = row.get("year")
    chapter = row.get("chapter")
    return (year is None, year or 0, chapter or 0, row.get("name") or row.get("event") or "")


def list_events(year_from=None, year_to=None):
    if _use_mock():
        rows = mock.EVENTS
        if year_from is not None:
            rows = [e for e in rows if e["year"] is not None and e["year"] >= year_from]
        if year_to is not None:
            rows = [e for e in rows if e["year"] is not None and e["year"] <= year_to]
        return sorted(rows, key=_event_sort_key)

    cypher = """
    MATCH (e:Event)
    WHERE ($year_from IS NULL OR e.year >= $year_from)
      AND ($year_to IS NULL OR e.year <= $year_to)
    OPTIONAL MATCH (e)-[:OCCURRED_AT]->(pl:Place)
    RETURN e.name AS name, e.year AS year, e.chapter AS chapter,
           e.result AS result, pl.name AS place
    ORDER BY e.year, e.chapter, e.name
    """
    return run_query(cypher, year_from=year_from, year_to=year_to)


def get_event(name):
    """事件详情：属性 + 地点 + 参与者（按角色、姓名排序）。不存在返回 None。"""
    if _use_mock():
        for e in mock.EVENTS:
            if e["name"] == name:
                data = dict(e)
                data["place"] = e.get("place", "")
                data["participants"] = [
                    {"name": p, "role": ""} for p in e.get("participants", [])
                ]
                return data
        return None

    cypher = """
    MATCH (e:Event {name: $name})
    OPTIONAL MATCH (e)-[:OCCURRED_AT]->(pl:Place)
    WITH e, pl
    OPTIONAL MATCH (p:Person)-[r:PARTICIPATED_IN]->(e)
    WITH e, pl,
         collect(DISTINCT {name: p.name, role: coalesce(r.role, '参与')}) AS ps
    RETURN e, pl.name AS place,
           [x IN ps WHERE x.name IS NOT NULL] AS participants
    """
    rows = run_query(cypher, name=name)
    if not rows:
        return None
    row = rows[0]
    data = dict(row["e"])
    data["place"] = row["place"]
    data["participants"] = sorted(
        row["participants"], key=lambda x: (x["role"] or "", x["name"] or "")
    )
    return data


def timeline(name):
    """人物生平时间线：按 (年份, 回目) 排序的事件列表。

    同年事件必须靠回目号区分先后——year 只有年份粒度，这是数据本身的限制。
    这里在 Python 侧再排一次，保证 mock 与真库两条路径的顺序一致。
    """
    if _use_mock():
        rows = [
            {
                "year": e["year"],
                "chapter": e["chapter"],
                "event": e["name"],
                "result": e["result"],
                "place": e.get("place", ""),
            }
            for e in mock.EVENTS
            if name in e.get("participants", [])
        ]
        return sorted(rows, key=_event_sort_key)

    cypher = """
    MATCH (p:Person {name: $name})-[:PARTICIPATED_IN]->(e:Event)
    OPTIONAL MATCH (e)-[:OCCURRED_AT]->(pl:Place)
    WITH e, collect(DISTINCT pl.name) AS places
    RETURN e.year AS year, e.chapter AS chapter, e.name AS event,
           e.result AS result, places[0] AS place
    """
    return sorted(run_query(cypher, name=name), key=_event_sort_key)
