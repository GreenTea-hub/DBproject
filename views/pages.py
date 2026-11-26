"""页面路由。负责人：P5（改路由需 P5 确认）。

页面只负责渲染模板，数据由浏览器端的 fetch 调 /api/* 获取，
这样页面和接口契约解耦，前端可以先用占位数据开发。
"""

from flask import Blueprint, render_template

bp = Blueprint("pages", __name__)


@bp.get("/")
def index():
    return render_template("index.html", active="home")


@bp.get("/person/<name>")
def person_page(name):
    return render_template("person.html", active="home", person_name=name)


@bp.get("/path")
def path_page():
    return render_template("path.html", active="path")


@bp.get("/factions")
def factions_page():
    return render_template("factions.html", active="factions")


@bp.get("/timeline")
def timeline_page():
    return render_template("timeline.html", active="timeline")


@bp.get("/admin")
def admin_page():
    return render_template("admin.html", active="admin")
