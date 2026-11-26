"""统一响应格式。负责人：P3。业务代码禁止手工拼字典返回。"""

from flask import jsonify


def ok(data=None, message=""):
    """成功：{"code": 0, "data": ..., "message": ""}"""
    return jsonify({"code": 0, "data": {} if data is None else data, "message": message})


def ok_page(items, total, page, size):
    """列表分页：{"code": 0, "data": {"items": [...], "total": n, "page": p, "size": s}}"""
    return ok({"items": items, "total": total, "page": page, "size": size})


def fail(code=400, message="请求有误"):
    """失败：HTTP 状态码 4xx/5xx，正文 {"code": 400, "message": "..."}"""
    return jsonify({"code": code, "message": message}), code
