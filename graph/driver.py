"""数据库连接与请求级会话管理。负责人：P3。

要点：
1. Driver 全局只建一次（Neo4j Driver 本身是线程安全的、内部维护连接池）；
2. Session 按请求创建，请求结束自动关闭，避免连接泄漏；
3. 端口 7687 只监听本机，Flask 与 Neo4j 同机部署。
"""

import logging

from flask import current_app, g, has_app_context

try:  # 本地未安装 neo4j 驱动时也能 import 成功，方便未装环境的同学先写前端
    from neo4j import GraphDatabase
except ImportError:  # pragma: no cover
    GraphDatabase = None

logger = logging.getLogger(__name__)

_driver = None


def get_driver():
    """全局唯一的 Driver，首次调用时创建。"""
    global _driver
    if _driver is not None:
        return _driver
    if GraphDatabase is None:
        raise RuntimeError("未安装 neo4j 驱动，请先 pip install -r requirements.txt")

    cfg = current_app.config
    _driver = GraphDatabase.driver(
        cfg["NEO4J_URI"],
        auth=(cfg["NEO4J_USER"], cfg["NEO4J_PASSWORD"]),
        max_connection_pool_size=50,
    )
    logger.info("Neo4j driver 已创建：%s", cfg["NEO4J_URI"])
    return _driver


def get_session():
    """一个请求一个会话，存在 flask.g 上，请求结束由 close_session 关闭。"""
    if not has_app_context():
        return get_driver().session()
    if "neo4j_session" not in g:
        g.neo4j_session = get_driver().session()
    return g.neo4j_session


def close_session(exc=None):
    """注册到 app.teardown_appcontext。"""
    if not has_app_context():
        return
    session = g.pop("neo4j_session", None)
    if session is not None:
        session.close()


def run_query(cypher, **params):
    """执行只读查询，返回 list[dict]。写入类请用 run_write。"""
    result = get_session().run(cypher, **params)
    return [record.data() for record in result]


def run_write(cypher, **params):
    """执行写入语句，返回摘要字典（节点/关系变更数），便于管理接口回显。"""
    result = get_session().run(cypher, **params)
    summary = result.consume()
    counters = summary.counters
    return {
        "nodes_created": counters.nodes_created,
        "nodes_deleted": counters.nodes_deleted,
        "relationships_created": counters.relationships_created,
        "relationships_deleted": counters.relationships_deleted,
        "properties_set": counters.properties_set,
    }


def ping():
    """连通性自检，部署手册与冒烟脚本都用它。"""
    try:
        get_session().run("RETURN 1 AS ok").single()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Neo4j 连接失败：%s", exc)
        return False


def close_driver():
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
