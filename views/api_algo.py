"""算法接口。负责人：P4。

GET /api/path?from=&to=&mode=shortest|weighted
GET /api/stats/pagerank
GET /api/stats/communities
GET /api/stats/smallworld?sample=
"""

from flask import Blueprint, request

from graph import queries_algo as query
from utils.response import fail, ok
from utils.validators import ParamError, clean_name, require, to_int

bp = Blueprint("algo", __name__, url_prefix="/api")


@bp.get("/path")
def shortest_path():
    try:
        require(request.args, "from", "to")
        source = clean_name(request.args.get("from"))
        target = clean_name(request.args.get("to"))
    except ParamError as exc:
        return fail(400, str(exc))

    mode = request.args.get("mode", "shortest")
    if mode not in ("shortest", "weighted"):
        return fail(400, "mode 只能是 shortest 或 weighted")

    data = query.shortest_path(source, target, mode)
    if not data.get("nodes"):
        return fail(404, "两人之间不存在路径")
    return ok(data)


@bp.get("/stats/pagerank")
def pagerank():
    try:
        limit = to_int(request.args.get("limit"), 10, 1, 100, field="limit")
    except ParamError as exc:
        return fail(400, str(exc))
    items = query.pagerank(limit)
    return ok({"items": items})


@bp.get("/stats/communities")
def communities():
    items = query.communities()
    return ok({"items": items})


@bp.get("/stats/smallworld")
def small_world():
    try:
        sample = to_int(request.args.get("sample"), 50, 5, 200, field="sample")
    except ParamError as exc:
        return fail(400, str(exc))
    return ok(query.small_world(sample))
