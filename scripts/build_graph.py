"""一键建库：建结构 -> 导入 -> 核对。负责人：P2。

与 import_graph.py 的关系：本脚本负责"按顺序把该做的事做完"，
单个步骤仍由 import_graph.py 提供，避免两处逻辑分叉。

用法：
    python scripts/build_graph.py            # 结构与数据全量重建（幂等，不删已有数据）
    python scripts/build_graph.py --reset    # 先清空库再导入（会二次确认）
    python scripts/build_graph.py --schema   # 只建约束与索引
    python scripts/build_graph.py --check    # 只做入库核对（部署手册第 5 节用）
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMPORT = ROOT / "scripts" / "import_graph.py"


def run(*args):
    cmd = [sys.executable, str(IMPORT), *args]
    print("$", " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        sys.exit(f"[失败] {' '.join(args) or '全量导入'}（退出码 {result.returncode}）")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="清空数据库后重建")
    parser.add_argument("--schema", action="store_true", help="只建约束与索引")
    parser.add_argument("--check", action="store_true", help="只做数量核对（部署手册第 5 节用）")
    args = parser.parse_args()

    if args.reset:
        answer = input("将清空 Neo4j 中所有节点与关系，输入 YES 继续：")
        if answer.strip() != "YES":
            sys.exit("已取消")
        from dotenv import load_dotenv
        import os
        from neo4j import GraphDatabase

        load_dotenv()
        driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687"),
            auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "")),
        )
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n").consume()
        driver.close()
        print("[reset] 已清空")

    if args.check:
        run("--check")
        return
    if args.schema:
        run("--schema")
        return

    run("--schema")
    run()
    run("--check")


if __name__ == "__main__":
    main()
