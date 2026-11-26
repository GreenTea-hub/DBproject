"""蓝图注册表。负责人：P3。

铁律：新增模块只能在 BLUEPRINTS 列表末尾追加一项，禁止调整已有顺序，
否则同一天合并的两个人会改到同一行，必然冲突。
"""

from .api_admin import bp as admin_bp
from .api_algo import bp as algo_bp
from .api_event import bp as event_bp
from .api_person import bp as person_bp
from .pages import bp as pages_bp

BLUEPRINTS = [
    pages_bp,
    person_bp,
    event_bp,
    algo_bp,
    admin_bp,
]


def register_blueprints(app):
    for bp in BLUEPRINTS:
        app.register_blueprint(bp)
