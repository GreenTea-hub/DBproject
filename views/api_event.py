"""事件与时间线接口。负责人：P2。

GET /api/events?year_from=&year_to=
GET /api/events/<name>
GET /api/timeline/<name>
"""

from flask import Blueprint, request

from graph import queries_event as query
from utils.response import fail, ok
from utils.validators import ParamError, clean_name, to_int

bp = Blueprint("event", __name__, url_prefix="/api")


@bp.get("/events")
def list_events():
    try:
        year_from = to_int(request.args.get("year_from"), None, field="year_from")
        year_to = to_int(request.args.get("year_to"), None, field="year_to")
    except ParamError as exc:
        return fail(400, str(exc))

    items = query.list_events(year_from, year_to)
    return ok({"items": items, "total": len(items)})


@bp.get("/events/<name>")
def event_detail(name):
    try:
        name = clean_name(name)
    except ParamError as exc:
        return fail(400, str(exc))

    data = query.get_event(name)
    if data is None:
        return fail(404, "事件不存在")
    return ok(data)


@bp.get("/timeline/<name>")
def person_timeline(name):
    try:
        name = clean_name(name)
    except ParamError as exc:
        return fail(400, str(exc))
    return ok({"items": query.timeline(name)})
