"""人物相关接口。负责人：P3。

GET /api/persons?q=&faction=&page=&size=
GET /api/persons/<name>
GET /api/persons/<name>/graph?depth=&types=
GET /api/persons/<name>/relations
"""

from flask import Blueprint, current_app, request

from graph import queries_person as query
from utils.response import fail, ok, ok_page
from utils.validators import (
    ParamError,
    clean_faction,
    clean_name,
    clean_relation_types,
    parse_page,
    to_int,
)

bp = Blueprint("person", __name__, url_prefix="/api/persons")


@bp.get("")
def list_persons():
    try:
        page, size = parse_page(
            request.args,
            default_size=current_app.config["DEFAULT_PAGE_SIZE"],
            max_size=current_app.config["MAX_PAGE_SIZE"],
        )
        faction = clean_faction(request.args.get("faction"))
    except ParamError as exc:
        return fail(400, str(exc))

    items, total = query.search_persons(
        q=request.args.get("q", "").strip(),
        faction=faction,
        page=page,
        size=size,
    )
    return ok_page(items, total, page, size)


@bp.get("/<name>")
def person_detail(name):
    try:
        name = clean_name(name)
    except ParamError as exc:
        return fail(400, str(exc))

    data = query.get_person(name)
    if data is None:
        return fail(404, "人物不存在")
    return ok(data)


@bp.get("/<name>/relations")
def person_relations(name):
    try:
        name = clean_name(name)
    except ParamError as exc:
        return fail(400, str(exc))

    items = query.list_relations(name)
    if items is None:
        return fail(404, "人物不存在")
    return ok({"items": items})


@bp.get("/<name>/graph")
def person_graph(name):
    try:
        name = clean_name(name)
        depth = to_int(request.args.get("depth"), current_app.config["DEFAULT_DEPTH"],
                       1, current_app.config["MAX_DEPTH"], field="depth")
    except ParamError as exc:
        return fail(400, str(exc))

    types = clean_relation_types(request.args.get("types"))
    data = query.person_subgraph(name, depth=depth, types=types)
    if data is None:
        return fail(404, "人物不存在")
    return ok(data)
