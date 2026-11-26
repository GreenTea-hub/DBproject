"""应用入口：创建 Flask 实例、注册蓝图、统一错误处理。负责人：P3。

本地启动：
    cp .env.example .env      # Windows: copy .env.example .env
    pip install -r requirements.txt
    python app.py             # 默认 http://127.0.0.1:5000

生产启动（Linux）：
    gunicorn -w 4 -b 0.0.0.0:5000 "app:create_app()"
"""

import logging

from flask import Flask, request
from werkzeug.exceptions import HTTPException

from config import Config
from graph import driver
from utils.response import fail, ok
from views import register_blueprints

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)
    app.json.ensure_ascii = False

    register_blueprints(app)
    register_error_handlers(app)

    # 请求结束关闭数据库会话，避免连接泄漏
    app.teardown_appcontext(driver.close_session)

    @app.get("/api/health")
    def health():
        """连通性自检：DB 不通也返回 200，但 db=false。"""
        if app.config.get("MOCK_DATA"):
            return ok({"service": "sanguo-graph", "db": None, "mock": True})
        return ok({"service": "sanguo-graph", "db": driver.ping(), "mock": False})

    return app


def register_error_handlers(app):
    @app.errorhandler(HTTPException)
    def handle_http_error(exc):
        if request.path.startswith("/api/"):
            return fail(exc.code, exc.description or "请求失败")
        return exc

    @app.errorhandler(Exception)
    def handle_unexpected_error(exc):
        app.logger.exception("未捕获异常：%s", exc)
        if request.path.startswith("/api/"):
            return fail(500, "服务器内部错误")
        return "服务器内部错误", 500


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=app.config["PORT"], debug=app.config["DEBUG"])
