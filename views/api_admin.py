"""管理接口：增删改与合并重复人物。负责人：P2。

POST   /api/persons
PUT    /api/persons/<name>
DELETE /api/persons/<name>
POST   /api/relations
DELETE /api/relations
POST   /api/persons/merge

状态码约定（docs/model.md 第 6 节）：
- 400 参数非法（字段、枚举、数值范围）
- 404 人物 / 关系不存在
- 409 人物或关系已存在，避免 MERGE 静默覆盖
- 201 新增成功
"""

from flask import Blueprint, request

from graph import queries_admin as query
from utils.response import fail, ok
from utils.validators import FACTIONS, RELATION_TYPES, ParamError, clean_name

bp = Blueprint("admin", __name__, url_prefix="/api")

PERSON_FIELDS = {"aliases", "faction", "role", "gender", "birth_year", "death_year"}


# ---------------------------------------------------------------- 参数校验

def _parse_aliases(value):
    """别名统一存成字符串数组：兼容前端用 | 分隔的字符串，也接受 JSON 数组。"""
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.replace("，", "|").split("|")
    elif isinstance(value, (list, tuple)):
        parts = [str(v) for v in value]
    else:
        raise ParamError("aliases 必须是字符串或字符串数组")

    result = []
    for part in parts:
        alias = part.strip()
        if alias and alias not in result:
            result.append(alias)
    if len(result) > 20:
        raise ParamError("aliases 最多 20 个")
    return result


def _text(value, field, max_len=32, default=""):
    if value is None:
        return default
    if not isinstance(value, str):
        raise ParamError(f"{field} 必须是字符串")
    value = value.strip()
    if len(value) > max_len:
        raise ParamError(f"{field} 长度不能超过 {max_len}")
    return value


def _int_in_range(value, field, minimum, maximum, default=None):
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise ParamError(f"{field} 必须是整数")
    try:
        num = int(value)
    except (TypeError, ValueError):
        raise ParamError(f"{field} 必须是整数")
    if not minimum <= num <= maximum:
        raise ParamError(f"{field} 必须在 {minimum}—{maximum} 之间")
    return num


def _float_in_range(value, field, minimum, maximum, default=None):
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise ParamError(f"{field} 必须是数字")
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ParamError(f"{field} 必须是数字")
    if not minimum <= num <= maximum:
        raise ParamError(f"{field} 必须在 {minimum}—{maximum} 之间")
    return num


def _faction(value, default="群雄"):
    if value is None or value == "":
        return default
    value = str(value).strip()
    if value not in FACTIONS:
        raise ParamError("阵营只能是：" + "、".join(FACTIONS))
    return value


def _gender(value):
    if value is None or value == "":
        return ""
    value = str(value).strip()
    if value not in ("男", "女"):
        raise ParamError("gender 只能是：男、女")
    return value


def _year(value, field):
    return _int_in_range(value, field, 1, 999, default=None)


def _person_payload(body):
    """新增人物时统一解析并校验字段，返回可直接交给查询层的字典。"""
    birth_year = _year(body.get("birth_year"), "birth_year")
    death_year = _year(body.get("death_year"), "death_year")
    if birth_year and death_year and birth_year > death_year:
        raise ParamError("birth_year 不能大于 death_year")
    return {
        "aliases": _parse_aliases(body.get("aliases")),
        "faction": _faction(body.get("faction")),
        "role": _text(body.get("role"), "role", max_len=16),
        "gender": _gender(body.get("gender")),
        "birth_year": birth_year,
        "death_year": death_year,
    }


# ---------------------------------------------------------------- 人物

@bp.post("/persons")
def create_person():
    body = request.get_json(silent=True) or {}
    try:
        name = clean_name(body.get("name"))
        payload = _person_payload(body)
    except ParamError as exc:
        return fail(400, str(exc))

    if query.person_exists(name):
        return fail(409, f"人物「{name}」已存在")

    data = query.create_person(name=name, **payload)
    return ok(data), 201


@bp.put("/persons/<name>")
def update_person(name):
    body = request.get_json(silent=True) or {}
    try:
        name = clean_name(name)
        unknown = [k for k in body if k not in PERSON_FIELDS and k != "name"]
        if unknown:
            raise ParamError("不支持修改字段：" + "、".join(sorted(unknown)))

        updates = {}
        if "aliases" in body:
            updates["aliases"] = _parse_aliases(body.get("aliases"))
        if "faction" in body:
            updates["faction"] = _faction(body.get("faction"))
        if "role" in body:
            updates["role"] = _text(body.get("role"), "role", max_len=16)
        if "gender" in body:
            updates["gender"] = _gender(body.get("gender"))
        if "birth_year" in body:
            updates["birth_year"] = _year(body.get("birth_year"), "birth_year")
        if "death_year" in body:
            updates["death_year"] = _year(body.get("death_year"), "death_year")
        if (updates.get("birth_year") and updates.get("death_year")
                and updates["birth_year"] > updates["death_year"]):
            raise ParamError("birth_year 不能大于 death_year")
        if not updates:
            raise ParamError("没有可更新的字段")
    except ParamError as exc:
        return fail(400, str(exc))

    if not query.person_exists(name):
        return fail(404, "人物不存在")

    return ok(query.update_person(name, updates))


@bp.delete("/persons/<name>")
def delete_person(name):
    try:
        name = clean_name(name)
    except ParamError as exc:
        return fail(400, str(exc))

    if not query.person_exists(name):
        return fail(404, "人物不存在")

    return ok(query.delete_person(name))


# ---------------------------------------------------------------- 关系

@bp.post("/relations")
def create_relation():
    body = request.get_json(silent=True) or {}
    try:
        source = clean_name(body.get("source"))
        target = clean_name(body.get("target"))
        rel_type = body.get("type")
        if rel_type not in RELATION_TYPES:
            raise ParamError("关系类型只能是：" + "、".join(RELATION_TYPES))
        if source == target:
            raise ParamError("关系的两端不能是同一人")
        weight = _int_in_range(body.get("weight"), "weight", 1, 100, default=50)
        confidence = _float_in_range(body.get("confidence"), "confidence", 0, 1, default=0.5)
        evidence = _text(body.get("evidence"), "evidence", max_len=500)
    except ParamError as exc:
        return fail(400, str(exc))

    missing = [n for n in (source, target) if not query.person_exists(n)]
    if missing:
        return fail(404, "人物不存在：" + "、".join(missing))

    if query.relation_exists(source, target):
        return fail(409, f"{source} 与 {target} 之间已存在关系，请先删除再新增")

    data = query.create_relation(
        source=source,
        target=target,
        rel_type=rel_type,
        weight=weight,
        evidence=evidence,
        confidence=confidence,
    )
    return ok(data), 201


@bp.delete("/relations")
def delete_relation():
    body = request.get_json(silent=True) or {}
    try:
        source = clean_name(body.get("source"))
        target = clean_name(body.get("target"))
        rel_type = body.get("type")
        if rel_type is not None and rel_type not in RELATION_TYPES:
            raise ParamError("关系类型只能是：" + "、".join(RELATION_TYPES))
    except ParamError as exc:
        return fail(400, str(exc))

    data = query.delete_relation(source, target, rel_type)
    if not data.get("deleted"):
        return fail(404, "关系不存在")
    return ok(data)


# ---------------------------------------------------------------- 合并

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

    missing = [n for n in (keep, drop) if not query.person_exists(n)]
    if missing:
        return fail(404, "人物不存在：" + "、".join(missing))

    data = query.merge_persons(keep, drop)
    if data.get("merged") is False:
        return fail(400, data.get("message") or "无法合并")
    return ok(data)
