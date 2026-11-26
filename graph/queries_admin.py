"""增删改与合并重复人物。负责人：P2。

要点：
1. 所有写入都用 MERGE + 参数，禁止字符串拼接，防 Cypher 注入；
2. 删除人物时必须同时清理关系，避免残留孤立边（冒烟检查会验这一条）；
3. 合并重复人物：把别名并入保留者，关系迁到保留者，再删除多余节点。
"""

from flask import current_app

from graph import mock
from graph.driver import run_write


def _use_mock():
    return bool(current_app.config.get("MOCK_DATA"))


def create_person(name, aliases=None, faction="群雄", role="", gender="", birth_year=None, death_year=None):
    if _use_mock():
        return mock.create_person(name, aliases, faction, role, gender, birth_year, death_year)

    cypher = """
    MERGE (p:Person {name: $name})
    SET p.aliases = $aliases,
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
    rows = run_write(cypher, name=name, aliases=aliases or [], faction=faction, role=role,
                     gender=gender, birth_year=birth_year, death_year=death_year)
    return {"name": name, **rows}


def update_person(name, fields):
    """只允许更新白名单字段。"""
    allowed = {"aliases", "faction", "role", "gender", "birth_year", "death_year"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return {"updated": 0}
    if _use_mock():
        return mock.update_person(name, updates)

    cypher = """
    MATCH (p:Person {name: $name})
    SET p += $updates
    RETURN p.name AS name
    """
    rows = run_write(cypher, name=name, updates=updates)
    return {"name": name, **rows}


def delete_person(name):
    """DETACH DELETE：连同关系一起删，保证无残留边。"""
    if _use_mock():
        return mock.delete_person(name)

    cypher = """
    MATCH (p:Person {name: $name})
    WITH p, count(p) AS found
    DETACH DELETE p
    RETURN found AS deleted
    """
    rows = run_write(cypher, name=name)
    return {"name": name, **rows}


def create_relation(source, target, rel_type, weight=50, evidence="", confidence=0.5):
    if _use_mock():
        return mock.create_relation(source, target, rel_type, weight, evidence, confidence)

    cypher = """
    MATCH (a:Person {name: $source}), (b:Person {name: $target})
    MERGE (a)-[r:RELATED_TO {type: $type}]->(b)
    SET r.weight = $weight, r.evidence = $evidence, r.confidence = $confidence
    RETURN a.name AS source, b.name AS target
    """
    rows = run_write(cypher, source=source, target=target, type=rel_type,
                     weight=weight, evidence=evidence, confidence=confidence)
    return {"source": source, "target": target, **rows}


def delete_relation(source, target, rel_type=None):
    if _use_mock():
        return mock.delete_relation(source, target, rel_type)

    cypher = """
    MATCH (a:Person {name: $source})-[r:RELATED_TO]->(b:Person {name: $target})
    WHERE $type IS NULL OR r.type = $type
    DELETE r
    """
    return run_write(cypher, source=source, target=target, type=rel_type)


def merge_persons(keep, drop):
    """把 drop 合并进 keep：别名合并、关系迁移、删除 drop。"""
    if _use_mock():
        return mock.merge_persons(keep, drop)

    cypher = """
    MATCH (keep:Person {name: $keep}), (drop:Person {name: $drop})
    SET keep.aliases = coalesce(keep.aliases, []) + [$drop] + coalesce(drop.aliases, [])
    WITH keep, drop
    MATCH (drop)-[r:RELATED_TO]-(o:Person)
    WHERE o <> keep
    MERGE (keep)-[nr:RELATED_TO {type: r.type}]->(o)
    SET nr.weight = coalesce(nr.weight, r.weight),
        nr.evidence = coalesce(nr.evidence, r.evidence),
        nr.confidence = coalesce(nr.confidence, r.confidence)
    WITH DISTINCT keep, drop
    DETACH DELETE drop
    RETURN keep.name AS name, keep.aliases AS aliases
    """
    rows = run_write(cypher, keep=keep, drop=drop)
    return {"keep": keep, "drop": drop, **rows}
