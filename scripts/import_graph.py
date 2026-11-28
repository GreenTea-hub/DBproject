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
if str(ROOT) not in sys.path:  # 让脚本在任意目录执行时都能 import utils
    sys.path.insert(0, str(ROOT))

from utils.validators import RELATION_TYPES  # noqa: E402

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
    bad_color = [r["name"] for r in rows if not (r.get("color") or "").startswith("#")]
    if bad_color:
        print(f"[警告] 阵营缺少合法颜色（#RRGGBB）：{'、'.join(bad_color)}")
    session.run(
        """
        UNWIND $rows AS row
        MERGE (f:Faction {name: row.name})
        SET f.color = row.color
        """,
        rows=rows,
    ).consume()
    print(f"[faction] {len(rows)} 个阵营")


def load_persons(session, rows, known_factions=None):
    empty_name = sum(1 for r in rows if not r.get("name"))
    if empty_name:
        print(f"[警告] persons.csv 有 {empty_name} 行缺少 name，已跳过")

    names = [r["name"] for r in rows if r.get("name")]
    duplicated = sorted({n for n in names if names.count(n) > 1})
    if duplicated:
        print(f"[警告] persons.csv 有重复人物名：{'、'.join(duplicated)}（MERGE 会合并为一人）")

    if known_factions:
        unknown = sorted({(r.get("faction") or "群雄") for r in rows} - set(known_factions))
        if unknown:
            print(f"[警告] 人物阵营未在 factions.csv 定义：{'、'.join(unknown)}"
                  "（仍会建 Faction 节点，但前端没有配色）")

    payload = [{
        "name": r["name"],
        "aliases": split_list(r.get("aliases")),
        "faction": r.get("faction") or "群雄",
        "role": r.get("role") or "",
        "gender": r.get("gender") or "",
        "birth_year": to_int(r.get("birth_year")),
        "death_year": to_int(r.get("death_year")),
    } for r in rows if r.get("name")]

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


def normalize_pair(source, target):
    """按 Unicode 顺序归一化方向，与 data/README 的 source < target 约定一致。"""
    return (source, target) if source <= target else (target, source)


def load_relations(session, rows, valid_persons):
    """导入关系：方向归一化 + 一对人物只保留一条边（取 weight 较大的那条）。

    不做归一化会出现 A→B 与 B→A 两条边，子图与最短路都会被重复边污染；
    data/README 已约定按 source < target 书写，脚本不能只依赖人工遵守。
    """
    seen = {}
    missing = set()
    skipped_missing = skipped_type = skipped_empty = duplicates = out_of_range = 0

    for r in rows:
        source = (r.get("source") or "").strip()
        target = (r.get("target") or "").strip()
        if not source or not target:
            skipped_empty += 1
            continue
        if source not in valid_persons or target not in valid_persons:
            missing.update(n for n in (source, target) if n not in valid_persons)
            skipped_missing += 1
            continue

        rel_type = (r.get("type") or "").strip()
        if rel_type not in RELATION_TYPES:
            skipped_type += 1
            continue

        weight = to_int(r.get("weight"), 50)
        if not 1 <= weight <= 100:
            weight = max(1, min(weight, 100))
            out_of_range += 1
        confidence = to_float(r.get("confidence"), 0.5)
        if not 0 <= confidence <= 1:
            confidence = max(0.0, min(confidence, 1.0))
            out_of_range += 1

        a, b = normalize_pair(source, target)
        record = {
            "source": a,
            "target": b,
            "type": rel_type,
            "weight": weight,
            "evidence": r.get("evidence") or "",
            "confidence": confidence,
        }
        previous = seen.get((a, b))
        if previous is None:
            seen[(a, b)] = record
        else:
            duplicates += 1
            if record["weight"] > previous["weight"]:
                seen[(a, b)] = record

    payload = list(seen.values())
    if missing:
        print(f"[警告] 关系引用了 persons.csv 中不存在的人物：{'、'.join(sorted(missing))}")
    if skipped_type:
        print(f"[警告] 跳过 {skipped_type} 行：type 不在 {' / '.join(RELATION_TYPES)} 内")
    if out_of_range:
        print(f"[警告] {out_of_range} 个 weight / confidence 越界，已截断到合法区间")

    for chunk in batched(payload):
        session.run(
            """
            UNWIND $rows AS row
            MATCH (a:Person {name: row.source})
            MATCH (b:Person {name: row.target})
            MERGE (a)-[r:RELATED_TO]-(b)
            SET r.type = row.type, r.weight = row.weight,
                r.evidence = row.evidence, r.confidence = row.confidence
            """,
            rows=chunk,
        ).consume()
    print(f"[relation] 输入 {len(rows)} 行 → 去重后 {len(payload)} 条"
          f"（重复 {duplicates}，缺人物 {skipped_missing}，非法类型 {skipped_type}，空行 {skipped_empty}）")


def load_events(session, rows, valid_persons):
    """事件同时挂 Chapter（IN_CHAPTER）与 Place（OCCURRED_AT），并挂参与者。

    参与者只 MATCH 已存在的人物，绝不用 MERGE 现场造节点：
    否则一个错别字就会生成没有阵营、没有别名的“影子人物”，污染全库。
    """
    events = []
    missing = set()
    bad_chapter = 0

    for r in rows:
        chapter_no = to_int(r.get("chapter"))
        if chapter_no is not None and not 1 <= chapter_no <= 120:
            bad_chapter += 1
        participants = []
        for item in split_list(r.get("participants")):
            person, _, role = item.partition(":")
            person = person.strip()
            if not person:
                continue
            if person not in valid_persons:
                missing.add(person)
                continue
            participants.append({"name": person, "role": role.strip() or "参与"})
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

    if bad_chapter:
        print(f"[警告] {bad_chapter} 个事件的回目号不在 1—120 内，请核对 events.csv")
    if missing:
        print(f"[警告] 事件参与者不在 persons.csv 中，已跳过：{'、'.join(sorted(missing))}")

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
            OPTIONAL MATCH (p:Person {name: part.name})
            FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END |
                MERGE (p)-[pr:PARTICIPATED_IN]->(e)
                SET pr.role = part.role
            )
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

CHECK_QUERY = """
MATCH (p:Person)
WITH count(p) AS persons
OPTIONAL MATCH (f:Faction)
WITH persons, count(f) AS factions
OPTIONAL MATCH (e:Event)
WITH persons, factions, count(e) AS events
OPTIONAL MATCH (c:Chapter)
WITH persons, factions, events, count(c) AS chapters
OPTIONAL MATCH ()-[r:RELATED_TO]->()
WITH persons, factions, events, chapters, count(r) AS relations
OPTIONAL MATCH (orphan:Person)
WHERE NOT (orphan)-[:RELATED_TO]-()
WITH persons, factions, events, chapters, relations, count(orphan) AS isolated
OPTIONAL MATCH (a:Person)-[:RELATED_TO]->(b:Person)
WHERE a.name > b.name
WITH persons, factions, events, chapters, relations, isolated, count(a) AS reversed
OPTIONAL MATCH (np:Person)
WHERE np.faction IS NULL OR np.faction = ''
WITH persons, factions, events, chapters, relations, isolated, reversed, count(np) AS no_faction
OPTIONAL MATCH (ee:Event)
WHERE NOT (ee)<-[:PARTICIPATED_IN]-()
RETURN persons, factions, events, chapters, relations, isolated,
       reversed, no_faction, count(ee) AS empty_events
"""


def check(session):
    row = session.run(CHECK_QUERY).single()
    if row is None:
        print("[check] 数据库为空")
        return None
    if row["persons"] == 0:
        print("[check] 数据库为空（0 个 Person）")
        return dict(row)

    print("\n[check] 入库核对")
    print(f"  Person           {row['persons']}")
    print(f"  Faction          {row['factions']}")
    print(f"  Event            {row['events']}")
    print(f"  Chapter          {row['chapters']}")
    print(f"  RELATED_TO       {row['relations']}")
    print(f"  孤立人物         {row['isolated']}")
    print(f"  反向关系边       {row['reversed']}（应为 0，非 0 说明数据绕过了导入脚本）")
    print(f"  缺阵营人物       {row['no_faction']}")
    print(f"  无参与者事件     {row['empty_events']}")
    return dict(row)


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
            factions = read_csv("factions.csv")
            persons = read_csv("persons.csv")
            valid_persons = {r["name"] for r in persons if r.get("name")}
            load_factions(session, factions)
            load_persons(session, persons, {f["name"] for f in factions})
            load_relations(session, read_csv("relations.csv"), valid_persons)
            load_events(session, read_csv("events.csv"), valid_persons)
            load_appears_in(session)
            check(session)
    finally:
        driver.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
