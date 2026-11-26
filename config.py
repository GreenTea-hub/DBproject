"""配置读取：所有敏感信息只在 .env，仓库内只有 .env.example。负责人：P3。"""

import os

from dotenv import load_dotenv

# 加载仓库根目录下的 .env（不存在时静默跳过，使用下面的默认值）
load_dotenv()


def _as_bool(value: str) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


class Config:
    # Flask
    PORT = int(os.getenv("FLASK_PORT", "5000"))
    DEBUG = _as_bool(os.getenv("FLASK_DEBUG", "0"))
    JSON_AS_ASCII = False

    # Neo4j
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

    # 占位数据：为 1 时不访问数据库，直接返回样例数据
    MOCK_DATA = _as_bool(os.getenv("MOCK_DATA", "1"))

    # 分页默认值，前后端都要按这个来
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100

    # 子图默认深度与上限（Cypher 中深度不能直接参数化，见 queries_person.py）
    DEFAULT_DEPTH = 1
    MAX_DEPTH = 3
