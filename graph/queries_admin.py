"""增删改与合并重复人物。负责人：P2。

约定（与 docs/model.md、docs/api.md 对齐）：
1. 所有写入都用 MERGE / 参数，禁止字符串拼接，防 Cypher 注入；
2. RELATED_TO 一对人物只保留一条边：写入时按人物名排序归一化方向（source < target），
   查询与删除一律按无向处理（Cypher 中不写箭头），避免 A→B 与 B→A 变成两条无关边；
3. 删除人物用 DETACH DELETE，保证不残留孤立边（冒烟检查会验这一条）；
4. 合并重复人物必须迁移四类关系（RELATED_TO / PARTICIPATED_IN / BELONGS_TO /
   APPEARS_IN），只删被合并的节点，不能丢掉事件、阵营与回目统计。
"""

from flask import current_app

from graph import mock
from graph.driver import run_query, run_write


def _use_mock():
    return bool(current_app.config.get("MOCK_DATA"))


def _ordered(source, target):
    """按 Unicode 顺序归一化一条边的两端，保证同一对人只有一个存储方向。"""
    return (source, target) if source <= target else (target, source)


def person_exists(name):
    """人物是否存在。接口层用它区分 404 / 409，避免 MERGE 静默覆盖已有节点。"""
    if _use_mock():
        return mock.detail(name) is not None
    rows = run_query(
        "MATCH (p:Person {name: $name}) RETURN p.name AS name LIMIT 1",
        name=name,
    )
    return bool(rows)


def relation_exists(source, target, rel_type=None):
    """两人之间是否已有关系（按无向判断，type 为 None 时不限类型）。"""
    if _use_mock():
        return any(
            {r["source"], r["target"]} == {source, target}
            and (rel_type is None or r["type"] == rel_type)
            for r in mock.RELATIONS
        )
    rows = run_query(
        """
        MATCH (a:Person {name: $source})-[r:RELATED_TO]-(b:Person {name: $target})
        WHERE $type IS NULL OR r.type = $type
        RETURN count(r) AS n
        """,
        source=source,
        target=target,
        type=rel_type,
    )
    return bool(rows and rows[0]["n"])


def create_person(name, aliases=None, faction="群雄", role="", gender="", birth_year=None, death_year=None):
    if _use_mock():
        mock.create_person(name, aliases, faction, role, gender, birth_year, death_year)
        return {"name": name, "created": True, "counters": {}, "mock": True}

    # 接口层已做存在性检查；这里用 ON CREATE，避免并发下静默覆盖已有属性
    cypher = """
    MERGE (p:Person {name: $name})
    ON CREATE SET p.aliases = $aliases,
                  p.faction = $faction,
                  p.role = $role,
                  p.gender = $gender,
                  p.birth_year = $birth_year,
                  p.death_year = $death_year
    WITH p
    MERGE (f:Faction {name: $faction})
    MERGE (p)-[:BELONGS_TO]->(f)
    RETURN p.name AS name
    """
    counters = run_write(
        cypher,
        name=name,
        aliases=aliases or [],
        faction=faction,
        role=role,
        gender=gender,
        birth_year=birth_year,
        death_year=death_year,
    )
    return {"name": name, "created": True, "counters": counters}


def update_person(name, fields):
    """只允许更新白名单字段；faction 变更时同步维护 BELONGS_TO，保持冗余字段一致。"""
    allowed = {"aliases", "faction", "role", "gender", "birth_year", "death_year"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return {"name": name, "updated": 0, "counters": {}}
    if _use_mock():
        mock.update_person(name, updates)
        return {"name": name, "updated": len(updates), "counters": {}, "mock": True}

    cypher = """
    MATCH (p:Person {name: $name})
    SET p += $updates
    WITH p, coalesce($updates.faction, p.faction) AS faction
    OPTIONAL MATCH (p)-[old:BELONGS_TO]->(:Faction)
    DELETE old
    WITH DISTINCT p, faction
    MERGE (f:Faction {name: faction})
    MERGE (p)-[:BELONGS_TO]->(f)
    RETURN p.name AS name
    """
    counters = run_write(cypher, name=name, updates=updates)
    return {"name": name, "updated": len(updates), "counters": counters}


def delete_person(name):
    """DETACH DELETE：连同关系一起删，保证无残留边。接口层已确认人物存在。"""
    if _use_mock():
        data = mock.delete_person(name)
        return {"name": name, "deleted": bool(data.get("deleted")), "counters": {}, "mock": True}

    cypher = """
    MATCH (p:Person {name: $name})
    DETACH DELETE p
    """
    counters = run_write(cypher, name=name)
    return {"name": name, "deleted": True, "counters": counters}


def create_relation(source, target, rel_type, weight=50, evidence="", confidence=0.5):
    """新增关系。一对人物只保留一条边，方向按 _ordered 归一化。"""
    source, target = _ordered(source, target)
    if _use_mock():
        mock.create_relation(source, target, rel_type, weight, evidence, confidence)
        return {"source": source, "target": target, "type": rel_type,
                "created": True, "counters": {}, "mock": True}

    cypher = """
    MATCH (a:Person {name: $source}), (b:Person {name: $target})
    MERGE (a)-[r:RELATED_TO]->(b)
    SET r.type = $type,
        r.weight = $weight,
        r.evidence = $evidence,
        r.confidence = $confidence
    RETURN a.name AS source, b.name AS target
    """
    counters = run_write(
        cypher,
        source=source,
        target=target,
        type=rel_type,
        weight=weight,
        evidence=evidence,
        confidence=confidence,
    )
    return {"source": source, "target": target, "type": rel_type,
            "created": True, "counters": counters}


def delete_relation(source, target, rel_type=None):
    """删除关系。按无向匹配：存储方向由写入时归一化决定，调用方不必关心顺序。"""
    if _use_mock():
        data = mock.delete_relation(source, target, rel_type)
        return {"source": source, "target": target, "type": rel_type,
                "deleted": data.get("deleted", 0), "mock": True}

    # 写语句需要回传统计，driver.run_write 只给计数器，这里用 run_query 取记录
    cypher = """
    MATCH (a:Person {name: $source})-[r:RELATED_TO]-(b:Person {name: $target})
    WHERE $type IS NULL OR r.type = $type
    WITH DISTINCT r
    WITH collect(r) AS rels
    FOREACH (x IN rels | DELETE x)
    RETURN size(rels) AS deleted
    """
    rows = run_query(cypher, source=source, target=target, type=rel_type)
    deleted = rows[0]["deleted"] if rows else 0
    return {"source": source, "target": target, "type": rel_type, "deleted": deleted}


def _mock_merge_persons(keep, drop):
    """mock 模式下的合并。

    不复用 mock.merge_persons：它先把 drop 的名字写进 keep.aliases，再调 delete_person，
    而 delete_person 内部按别名查找，会把保留者删掉（P3 的占位实现，需同步给 P3 修）。
    这里按真库 Cypher 的语义实现一遍：别名去重、关系迁移去重、事件参与者替换、按主名删除。
    """
    keep_person = mock.detail(keep)
    drop_person = mock.detail(drop)
    if keep_person is None or drop_person is None:
        return {"keep": keep, "drop": drop, "merged": False, "message": "人物不存在"}
    if keep_person["name"] == drop_person["name"]:
        return {"keep": keep, "drop": drop, "merged": False, "message": "两人指向同一人物"}

    keep_name, drop_name = keep_person["name"], drop_person["name"]
    related = sum(1 for r in mock.RELATIONS if drop_name in (r["source"], r["target"]))
    events = sum(1 for e in mock.EVENTS if drop_name in (e.get("participants") or []))

    aliases = []
    for alias in list(keep_person.get("aliases") or []) + [drop_name] + list(drop_person.get("aliases") or []):
        if alias != keep_name and alias not in aliases:
            aliases.append(alias)
    keep_person["aliases"] = aliases

    by_pair = {}
    for rel in mock.RELATIONS:
        source = keep_name if rel["source"] == drop_name else rel["source"]
        target = keep_name if rel["target"] == drop_name else rel["target"]
        if source == target:  # drop 与 keep 之间的边在合并后变成自环，直接丢弃
            continue
        pair = tuple(sorted((source, target)))
        previous = by_pair.get(pair)
        # 一对人物只保留一条边，权重大的胜出，与真库 Cypher 的 ON MATCH 规则一致
        if previous is None or rel.get("weight", 0) > previous.get("weight", 0):
            by_pair[pair] = {**rel, "source": source, "target": target}
    mock.RELATIONS[:] = list(by_pair.values())

    for event in mock.EVENTS:
        participants = event.get("participants") or []
        if drop_name not in participants:
            continue
        replaced = []
        for person in participants:
            person = keep_name if person == drop_name else person
            if person not in replaced:
                replaced.append(person)
        event["participants"] = replaced

    mock.PERSONS[:] = [p for p in mock.PERSONS if p["name"] != drop_name]
    return {
        "keep": keep_name,
        "drop": drop_name,
        "aliases": aliases,
        "migrated": {"relations": related, "events": events, "chapters": 0, "factions": 0},
        "merged": True,
        "mock": True,
    }


def merge_persons(keep, drop):
    """把 drop 合并进 keep：别名并入、四类关系迁移、删除 drop。

    整条语句是一个事务：中途失败不会留下“别名已改、关系没迁”的半成品。
    合并规则：
      - 别名：keep.aliases + drop 的名字 + drop.aliases，去重、保持顺序；
      - RELATED_TO：按无向迁移，同类型边取 weight / confidence 较大者，evidence 取较长者；
      - PARTICIPATED_IN：保留 keep 已有的角色，缺失时补上 drop 的角色；
      - APPEARS_IN：同一回目的 count 相加；
      - BELONGS_TO：keep 已有阵营则保留，没有才继承 drop 的。
    """
    if _use_mock():
        return _mock_merge_persons(keep, drop)

    cypher = """
    MATCH (keep:Person {name: $keep}), (drop:Person {name: $drop})
    WHERE keep <> drop
    SET keep.aliases = reduce(
          acc = [],
          x IN coalesce(keep.aliases, []) + [$drop] + coalesce(drop.aliases, [])
          | CASE WHEN x = $keep OR x IN acc THEN acc ELSE acc + x END
        )
    WITH keep, drop
    CALL {
      WITH keep, drop
      MATCH (drop)-[r:RELATED_TO]-(o:Person)
      WHERE o <> keep AND o <> drop
      WITH keep, o, r,
           CASE WHEN keep.name < o.name THEN keep ELSE o END AS a,
           CASE WHEN keep.name < o.name THEN o ELSE keep END AS b
      MERGE (a)-[nr:RELATED_TO]-(b)
      ON CREATE SET nr.type = r.type,
                    nr.weight = r.weight,
                    nr.evidence = r.evidence,
                    nr.confidence = r.confidence
      ON MATCH SET nr.weight = CASE WHEN coalesce(r.weight, 0) > coalesce(nr.weight, 0)
                                    THEN r.weight ELSE nr.weight END,
                   nr.confidence = CASE WHEN coalesce(r.confidence, 0) > coalesce(nr.confidence, 0)
                                        THEN r.confidence ELSE nr.confidence END,
                   nr.evidence = CASE WHEN size(coalesce(r.evidence, '')) > size(coalesce(nr.evidence, ''))
                                      THEN r.evidence ELSE nr.evidence END
      RETURN count(*) AS related
    }
    CALL {
      WITH keep, drop
      MATCH (drop)-[pe:PARTICIPATED_IN]->(e:Event)
      MERGE (keep)-[npe:PARTICIPATED_IN]->(e)
      ON CREATE SET npe.role = pe.role
      RETURN count(*) AS events
    }
    CALL {
      WITH keep, drop
      MATCH (drop)-[ap:APPEARS_IN]->(c:Chapter)
      MERGE (keep)-[nap:APPEARS_IN]->(c)
      ON CREATE SET nap.count = coalesce(ap.count, 0)
      ON MATCH SET nap.count = coalesce(nap.count, 0) + coalesce(ap.count, 0)
      RETURN count(*) AS chapters
    }
    CALL {
      WITH keep, drop
      MATCH (drop)-[:BELONGS_TO]->(f:Faction)
      WHERE NOT (keep)-[:BELONGS_TO]->(:Faction)
      MERGE (keep)-[:BELONGS_TO]->(f)
      RETURN count(*) AS factions
    }
    WITH keep, drop, related, events, chapters, factions
    DETACH DELETE drop
    RETURN keep.name AS name, keep.aliases AS aliases,
           related, events, chapters, factions
    """
    rows = run_query(cypher, keep=keep, drop=drop)
    if not rows:
        return {"keep": keep, "drop": drop, "merged": False,
                "message": "人物不存在", "aliases": [], "migrated": {}}
    row = rows[0]
    return {
        "keep": keep,
        "drop": drop,
        "merged": True,
        "aliases": row["aliases"],
        "migrated": {
            "relations": row["related"],
            "events": row["events"],
            "chapters": row["chapters"],
            "factions": row["factions"],
        },
    }
