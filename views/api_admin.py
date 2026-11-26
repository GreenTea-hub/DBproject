"""管理接口：增删改与合并重复人物。负责人：P2。

POST   /api/persons
PUT    /api/persons/<name>
DELETE /api/persons/<name>
POST   /api/relations
DELETE /api/relations
POST   /api/persons/merge
"""

from flask import Blueprint, request

from graph import queries_admin as query
from utils.response import fail, ok
from utils.validators import RELATION_TYPES, ParamError, clean_name

bp = Blueprint("admin", __name__, url_prefix="/api")


@bp.post("/persons")
def create_person():
    body = request.get_json(silent=True) or {}
    try:
        name = clean_name(body.get("name"))
    except ParamError as exc:
        return fail(400, str(exc))

    aliases = body.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [a for a in aliases.replace("，", "|").split("|") if a]

    data = query.create_person(
        name=name,
        aliases=aliases,
        faction=body.get("faction", "群雄"),
        role=body.get("role", ""),
        gender=body.get("gender", ""),
        birth_year=body.get("birth_year"),
        death_year=body.get("death_year"),
    )
    return ok(data), 201


@bp.put("/persons/<name>")
def update_person(name):
    body = request.get_json(silent=True) or {}
    try:
        name = clean_name(name)
    except ParamError as exc:
        return fail(400, str(exc))
    return ok(query.update_person(name, body))


@bp.delete("/persons/<name>")
def delete_person(name):
    try:
        name = clean_name(name)
    except ParamError as exc:
        return fail(400, str(exc))
    return ok(query.delete_person(name))


@bp.post("/relations")
def create_relation():
    body = request.get_json(silent=True) or {}
    try:
        source = clean_name(body.get("source"))
        target = clean_name(body.get("target"))
    except ParamError as exc:
        return fail(400, str(exc))

    rel_type = body.get("type")
    if rel_type not in RELATION_TYPES:
        return fail(400, "关系类型只能是：" + "、".join(RELATION_TYPES))

    data = query.create_relation(
        source=source,
        target=target,
        rel_type=rel_type,
        weight=int(body.get("weight", 50)),
        evidence=body.get("evidence", ""),
        confidence=float(body.get("confidence", 0.5)),
    )
    return ok(data), 201


@bp.delete("/relations")
def delete_relation():
    body = request.get_json(silent=True) or {}
    try:
        source = clean_name(body.get("source"))
        target = clean_name(body.get("target"))
    except ParamError as exc:
        return fail(400, str(exc))
    return ok(query.delete_relation(source, target, body.get("type")))


@bp.post("/persons/merge")
def merge_persons():
    body = request.get_json(silent=True) or {}
    try:
        keep = clean_name(body.get("keep"))
        drop = clean_name(body.get("drop"))
    except ParamError as exc:
        return fail(400, str(exc))
    if keep == drop:
        return fail(400, "keep 与 drop 不能是同一人")
    return ok(query.merge_persons(keep, drop))
