"""数据入库。负责人：P2。

流程：建约束索引 -> 导入 Faction -> Chapter -> Person -> RELATED_TO
      -> Event / Place / PARTICIPATED_IN / OCCURRED_AT / IN_CHAPTER -> APPEARS_IN
      -> 与 CSV 行数逐项对账。

用法：
    python scripts/import_graph.py              # 全量导入（可重复执行，MERGE 保证幂等）
    python scripts/import_graph.py --schema     # 只建约束与索引
    python scripts/import_graph.py --check      # 只做入库后的数量核对

数据来源：data/factions.csv、persons.csv、relations.csv、events.csv
          （列定义见 data/README.md，格式由 P1 与 P2 在第 9 周共同定死）
可选来源：data/build/chapters.csv（回目与标题）、data/build/mentions.csv（人物出现回目），
          均由 P1 的 scripts/split_chapters.py 与 scripts/extract_mentions.py 生成。
          缺失时不影响导入，但 Chapter 只有事件涉及的几十回、且标题为空。

退出码：0 正常；1 数据不一致或对账未通过（便于 CI / build_graph.py 判断）
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
BUILD = DATA / "build"
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


def load_chapters(session, rows):
    """120 回全部入库，带回目名。事件只涉及 70 回，缺了这一段时间线会残缺。"""
    payload = [{
        "no": to_int(r.get("no")),
        "title": r.get("title") or "",
        "chars": to_int(r.get("chars"), 0),
    } for r in rows if to_int(r.get("no")) is not None]

    for chunk in batched(payload):
        session.run(
            """
            UNWIND $rows AS row
            MERGE (c:Chapter {no: row.no})
            SET c.title = row.title, c.chars = row.chars
            """,
            rows=chunk,
        ).consume()
    print(f"[chapter] {len(payload)} 回")


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


def load_relations(session, rows, known):
    """关系两端必须都在词典里；MERGE 带 type，同两人不同关系类型不会互相覆盖。"""
    payload, missing = [], []
    for r in rows:
        for side in ("source", "target"):
            if r[side] not in known:
                missing.append(f"{r['source']}-{r['target']}：{side}={r[side]}")
        payload.append({
            "source": r["source"],
            "target": r["target"],
            "type": r["type"],
            "weight": to_int(r.get("weight"), 50),
            "evidence": r.get("evidence") or "",
            "confidence": to_float(r.get("confidence"), 0.5),
        })
    if missing:
        sys.exit("[错误] relations.csv 引用了词典外的人物（先跑 extract_mentions.py --validate）：\n  "
                 + "\n  ".join(missing[:10]))

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


def load_events(session, rows, known):
    """事件同时挂 Chapter（IN_CHAPTER）与 Place（OCCURRED_AT），并挂参与者。

    参与者用 MATCH 而非 MERGE：事件里出现词典外的人名属于数据错误，
    直接报错退出，避免在库里留下没有阵营、没有关系的"幽灵人物"。
    """
    events, missing = [], []
    for r in rows:
        participants = []
        for item in split_list(r.get("participants")):
            person, _, role = item.partition(":")
            if not person:
                continue
            if person not in known:
                missing.append(f"{r['name']} -> {person}")
            participants.append({"name": person, "role": role or "参与"})
        events.append({
            "name": r["name"],
            "year": to_int(r.get("year")),
            "chapter": to_int(r.get("chapter")),
            "result": r.get("result") or "",
            "place": r.get("place") or "",
            "participants": participants,
        })
    if missing:
        sys.exit("[错误] events.csv 的参与者不在词典中（先跑 extract_mentions.py --validate）：\n  "
                 + "\n  ".join(missing[:10]))

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
            WITH e, part
            WHERE part IS NOT NULL
            MATCH (p:Person {name: part.name})
            MERGE (p)-[pr:PARTICIPATED_IN]->(e)
            SET pr.role = part.role
            """,
            rows=chunk,
        ).consume()
    print(f"[event] {len(events)} 个事件")


def load_appears_in(session):
    """APPEARS_IN：读取 P1 产出的 data/build/mentions.csv（回目,人物,次数）。"""
    path = BUILD / "mentions.csv"
    if not path.exists():
        print("[appears_in] 跳过（未找到 data/build/mentions.csv，先跑 extract_mentions.py）")
        return 0
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = [{
            "chapter": to_int(r.get("chapter")),
            "person": (r.get("person") or "").strip(),
            "count": to_int(r.get("count"), 0),
        } for r in csv.DictReader(f)]
    rows = [r for r in rows if r["chapter"] is not None and r["person"]]

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
    return len(rows)


# ---------------------------------------------------------------- 核对

# 逐条单查：避免 MATCH 串联造成的笛卡尔积，也不会出现"聚合跳过空值"的告警
COUNTS = [
    ("Person", "MATCH (n:Person) RETURN count(n) AS n"),
    ("Faction", "MATCH (n:Faction) RETURN count(n) AS n"),
    ("Chapter", "MATCH (n:Chapter) RETURN count(n) AS n"),
    ("Event", "MATCH (n:Event) RETURN count(n) AS n"),
    ("Place", "MATCH (n:Place) RETURN count(n) AS n"),
    ("RELATED_TO", "MATCH ()-[r:RELATED_TO]->() RETURN count(r) AS n"),
    ("BELONGS_TO", "MATCH ()-[r:BELONGS_TO]->() RETURN count(r) AS n"),
    ("PARTICIPATED_IN", "MATCH ()-[r:PARTICIPATED_IN]->() RETURN count(r) AS n"),
    ("OCCURRED_AT", "MATCH ()-[r:OCCURRED_AT]->() RETURN count(r) AS n"),
    ("IN_CHAPTER", "MATCH ()-[r:IN_CHAPTER]->() RETURN count(r) AS n"),
    ("APPEARS_IN", "MATCH ()-[r:APPEARS_IN]->() RETURN count(r) AS n"),
]

HEALTH = [
    ("孤立人物（无任何关系）", "MATCH (p:Person) WHERE NOT (p)-[:RELATED_TO]-() RETURN count(p) AS n", 0),
    ("无阵营人物（幽灵节点）", "MATCH (p:Person) WHERE p.faction IS NULL RETURN count(p) AS n", 0),
    ("无参与人的事件", "MATCH (e:Event) WHERE NOT (:Person)-[:PARTICIPATED_IN]->(e) RETURN count(e) AS n", 0),
    ("无地点的事件", "MATCH (e:Event) WHERE NOT (e)-[:OCCURRED_AT]->() RETURN count(e) AS n", 0),
    ("无事件也无人物出现的回", "MATCH (c:Chapter) WHERE NOT (c)<-[:IN_CHAPTER]-() AND NOT (c)<-[:APPEARS_IN]-() RETURN count(c) AS n", 0),
    ("标题为空的回", "MATCH (c:Chapter) WHERE c.title IS NULL OR c.title = '' RETURN count(c) AS n", 0),
]


def check(session, expected=None):
    """打印节点/关系计数；给了 expected 就顺带对账，不一致返回 False。"""
    actual = {}
    for label, cypher in COUNTS:
        actual[label] = session.run(cypher).single()["n"]

    print("\n[check] 入库核对")
    print(f"  {'':16}{'实际':>6}{'期望':>8}")
    ok = True
    for label, _ in COUNTS:
        want = (expected or {}).get(label)
        if want is None:
            print(f"  {label:16}{actual[label]:>6}")
            continue
        flag = "" if want == actual[label] else "   <-- 不一致"
        if flag:
            ok = False
        print(f"  {label:16}{actual[label]:>6}{want:>8}{flag}")

    print("\n[check] 数据健康度")
    for label, cypher, want in HEALTH:
        n = session.run(cypher).single()["n"]
        flag = "" if n == want else "   <-- 需处理"
        if n != want and label != "无事件也无人物出现的回":
            ok = False
        print(f"  {label:22}{n:>6}{flag}")

    print("\n[check] " + ("全部一致" if ok else "存在不一致，检查上方标记行"))
    return ok


# ---------------------------------------------------------------- 主流程

def main():
    parser = argparse.ArgumentParser(description="导入三国图数据到 Neo4j")
    parser.add_argument("--schema", action="store_true", help="只建约束与索引")
    parser.add_argument("--check", action="store_true", help="只做数量核对")
    args = parser.parse_args()

    driver = driver_from_env()
    exit_code = 0
    try:
        with driver.session() as session:
            session.run("RETURN 1").consume()
            print("[连接] Neo4j OK")

            if args.check:
                return 0 if check(session) else 1

            if args.schema:
                apply_schema(session)
                return 0

            factions = read_csv("factions.csv")
            persons = read_csv("persons.csv")
            relations = read_csv("relations.csv")
            events = read_csv("events.csv")
            known = {p["name"] for p in persons}

            apply_schema(session)
            load_factions(session, factions)
            if (BUILD / "chapters.csv").exists():
                load_chapters(session, [
                    {(k or "").strip(): (v or "").strip() for k, v in row.items()}
                    for row in csv.DictReader((BUILD / "chapters.csv").open(encoding="utf-8-sig", newline=""))
                ])
            else:
                print("[chapter] 跳过（未找到 data/build/chapters.csv，先跑 split_chapters.py）")
            load_persons(session, persons)
            load_relations(session, relations, known)
            load_events(session, events, known)
            appears = load_appears_in(session)

            expected = {
                "Person": len(persons),
                "Faction": len(factions),
                "Event": len(events),
                "RELATED_TO": len(relations),
            }
            if (BUILD / "chapters.csv").exists():
                expected["Chapter"] = 120
            if appears:
                expected["APPEARS_IN"] = appears

            if not check(session, expected):
                exit_code = 1
    finally:
        driver.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
