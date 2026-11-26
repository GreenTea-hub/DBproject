"""数据入库。负责人：P2。

流程：建约束索引 -> 导入 Faction/Person -> 导入 Chapter/Event/Place
      -> 导入 RELATED_TO / PARTICIPATED_IN / OCCURRED_AT / IN_CHAPTER / BELONGS_TO
      -> 打印节点与关系数量核对。

用法：
    python scripts/import_graph.py              # 全量导入（可重复执行，MERGE 保证幂等）
    python scripts/import_graph.py --schema     # 只建约束与索引
    python scripts/import_graph.py --check      # 只做入库后的数量核对

数据来源：data/persons.csv、factions.csv、relations.csv、events.csv
（列定义见 data/README.md，格式由 P1 与 P2 在第 9 周共同定死）
"""

import argparse
import csv
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SCHEMA = ROOT / "graph" / "schema.cypher"

BATCH = 500


# ---------------------------------------------------------------- 工具

def read_csv(name):
    path = DATA / name
    if not path.exists():
        sys.exit(f"[错误] 缺少数据文件：{path}")
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [{(k or "").strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def to_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def split_list(value):
    return [v for v in (value or "").replace("，", "|").split("|") if v]


def batched(rows, size=BATCH):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def driver_from_env():
    load_dotenv()
    uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "")
    if not password:
        sys.exit("[错误] 未配置 NEO4J_PASSWORD，请先复制 .env.example 为 .env")
    return GraphDatabase.driver(uri, auth=(user, password))


# ---------------------------------------------------------------- 建库结构

def apply_schema(session):
    if not SCHEMA.exists():
        sys.exit(f"[错误] 找不到建库脚本：{SCHEMA}")
    statements = []
    for raw in SCHEMA.read_text(encoding="utf-8").split(";"):
        stmt = "\n".join(line for line in raw.splitlines() if not line.strip().startswith("//")).strip()
        if stmt and not stmt.upper().startswith("SHOW"):
            statements.append(stmt)
    for stmt in statements:
        session.run(stmt).consume()
    print(f"[schema] 已应用 {len(statements)} 条约束/索引语句")


# ---------------------------------------------------------------- 各类节点

def load_factions(session, rows):
    session.run(
        """
        UNWIND $rows AS row
        MERGE (f:Faction {name: row.name})
        SET f.color = row.color
        """,
        rows=rows,
    ).consume()
    print(f"[faction] {len(rows)} 个阵营")


def load_persons(session, rows):
    payload = [{
        "name": r["name"],
        "aliases": split_list(r.get("aliases")),
        "faction": r.get("faction") or "群雄",
        "role": r.get("role") or "",
        "gender": r.get("gender") or "",
        "birth_year": to_int(r.get("birth_year")),
        "death_year": to_int(r.get("death_year")),
    } for r in rows]

    for chunk in batched(payload):
        session.run(
            """
            UNWIND $rows AS row
            MERGE (p:Person {name: row.name})
            SET p.aliases = row.aliases,
                p.faction = row.faction,
                p.role = row.role,
                p.gender = row.gender,
                p.birth_year = row.birth_year,
                p.death_year = row.death_year
            WITH p, row
            MERGE (f:Faction {name: row.faction})
            MERGE (p)-[:BELONGS_TO]->(f)
            """,
            rows=chunk,
        ).consume()
    print(f"[person] {len(payload)} 人")


def load_relations(session, rows):
    payload = [{
        "source": r["source"],
        "target": r["target"],
        "type": r["type"],
        "weight": to_int(r.get("weight"), 50),
        "evidence": r.get("evidence") or "",
        "confidence": to_float(r.get("confidence"), 0.5),
    } for r in rows]

    for chunk in batched(payload):
        session.run(
            """
            UNWIND $rows AS row
            MATCH (a:Person {name: row.source})
            MATCH (b:Person {name: row.target})
            MERGE (a)-[r:RELATED_TO {type: row.type}]->(b)
            SET r.weight = row.weight, r.evidence = row.evidence, r.confidence = row.confidence
            """,
            rows=chunk,
        ).consume()
    print(f"[relation] {len(payload)} 条关系")


def load_events(session, rows):
    """事件同时挂 Chapter（IN_CHAPTER）与 Place（OCCURRED_AT），并挂参与者。"""
    events = []
    for r in rows:
        chapter_no = to_int(r.get("chapter"))
        participants = []
        for item in split_list(r.get("participants")):
            person, _, role = item.partition(":")
            if person:
                participants.append({"name": person, "role": role or "参与"})
        events.append({
            "name": r["name"],
            "year": to_int(r.get("year")),
            "chapter": chapter_no,
            "result": r.get("result") or "",
            "place": r.get("place") or "",
            "participants": participants,
        })

    for chunk in batched(events):
        session.run(
            """
            UNWIND $rows AS row
            MERGE (e:Event {name: row.name})
            SET e.year = row.year, e.chapter = row.chapter, e.result = row.result
            WITH e, row
            FOREACH (_ IN CASE WHEN row.chapter IS NULL THEN [] ELSE [1] END |
                MERGE (c:Chapter {no: row.chapter})
                ON CREATE SET c.title = ''
                MERGE (e)-[:IN_CHAPTER]->(c)
            )
            FOREACH (_ IN CASE WHEN row.place = '' THEN [] ELSE [1] END |
                MERGE (pl:Place {name: row.place})
                MERGE (e)-[:OCCURRED_AT]->(pl)
            )
            WITH e, row
            UNWIND (CASE WHEN size(row.participants) = 0 THEN [null] ELSE row.participants END) AS part
            FOREACH (_ IN CASE WHEN part IS NULL THEN [] ELSE [1] END |
                MERGE (p:Person {name: part.name})
                MERGE (p)-[pr:PARTICIPATED_IN]->(e)
                SET pr.role = part.role
            )
            """,
            rows=chunk,
        ).consume()
    print(f"[event] {len(events)} 个事件")


def load_appears_in(session):
    """APPEARS_IN：可选，读取 P1 产出的 data/build/mentions.csv（回目,人物,次数）。"""
    path = DATA / "build" / "mentions.csv"
    if not path.exists():
        print("[appears_in] 跳过（未找到 data/build/mentions.csv）")
        return
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = [{
            "chapter": to_int(r.get("chapter")),
            "person": (r.get("person") or "").strip(),
            "count": to_int(r.get("count"), 0),
        } for r in csv.DictReader(f)]

    for chunk in batched(rows):
        session.run(
            """
            UNWIND $rows AS row
            MATCH (p:Person {name: row.person})
            MERGE (c:Chapter {no: row.chapter})
            MERGE (p)-[a:APPEARS_IN]->(c)
            SET a.count = row.count
            """,
            rows=chunk,
        ).consume()
    print(f"[appears_in] {len(rows)} 条出现记录")


# ---------------------------------------------------------------- 核对

CHECK_QUERY = """
MATCH (p:Person) WITH count(p) AS persons
MATCH (f:Faction) WITH persons, count(f) AS factions
MATCH (e:Event) WITH persons, factions, count(e) AS events
MATCH (c:Chapter) WITH persons, factions, events, count(c) AS chapters
MATCH ()-[r:RELATED_TO]->() WITH persons, factions, events, chapters, count(r) AS relations
OPTIONAL MATCH (orphan:Person) WHERE NOT (orphan)-[:RELATED_TO]-()
RETURN persons, factions, events, chapters, relations, count(orphan) AS isolated
"""


def check(session):
    row = session.run(CHECK_QUERY).single()
    if row is None:
        print("[check] 数据库为空")
        return
    print("\n[check] 入库核对")
    print(f"  Person           {row['persons']}")
    print(f"  Faction          {row['factions']}")
    print(f"  Event            {row['events']}")
    print(f"  Chapter          {row['chapters']}")
    print(f"  RELATED_TO       {row['relations']}")
    print(f"  孤立人物         {row['isolated']}")


# ---------------------------------------------------------------- 主流程

def main():
    parser = argparse.ArgumentParser(description="导入三国图数据到 Neo4j")
    parser.add_argument("--schema", action="store_true", help="只建约束与索引")
    parser.add_argument("--check", action="store_true", help="只做数量核对")
    args = parser.parse_args()

    driver = driver_from_env()
    try:
        with driver.session() as session:
            session.run("RETURN 1").consume()
            print("[连接] Neo4j OK")

            if args.check:
                check(session)
                return
            if args.schema:
                apply_schema(session)
                return

            apply_schema(session)
            load_factions(session, read_csv("factions.csv"))
            load_persons(session, read_csv("persons.csv"))
            load_relations(session, read_csv("relations.csv"))
            load_events(session, read_csv("events.csv"))
            load_appears_in(session)
            check(session)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
