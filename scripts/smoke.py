"""冒烟检查：只判断"通不通"，不判断"内容对不对"。负责人：P3。

全组每次合并前必须跑一遍，全绿才允许合并；失败行贴到群里，由第一责任人当天修。
默认检查本机 5000 端口，可通过环境变量 SMOKE_BASE_URL 指向服务器。

用法：
    python app.py                 # 另开一个终端先把服务跑起来
    python scripts/smoke.py
"""

import os
import sys

import requests

BASE = os.getenv("SMOKE_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
TIMEOUT = 10

# (名称, 方法, 路径, JSON 体, 第一责任人, 校验函数)
CHECKS = []


def check(name, owner):
    def wrapper(fn):
        CHECKS.append((name, owner, fn))
        return fn
    return wrapper


def get_json(path, **params):
    resp = requests.get(BASE + path, params=params, timeout=TIMEOUT)
    return resp


def assert_envelope(resp, *keys):
    assert resp.status_code == 200, f"HTTP {resp.status_code}"
    body = resp.json()
    assert body.get("code") == 0, f"code={body.get('code')} message={body.get('message')}"
    data = body.get("data") or {}
    for key in keys:
        assert key in data, f"返回缺少字段 {key}"
    return data


@check("首页可访问", "P5")
def home():
    resp = requests.get(BASE + "/", timeout=TIMEOUT)
    assert resp.status_code == 200, f"HTTP {resp.status_code}"


@check("人物搜索接口", "P3")
def search_persons():
    data = assert_envelope(get_json("/api/persons", q="刘", size=5), "items", "total")
    assert isinstance(data["items"], list), "items 不是列表"


@check("人物详情接口", "P3")
def person_detail():
    assert_envelope(get_json("/api/persons/刘备"), "name", "aliases")


@check("人物子图接口", "P3")
def person_graph():
    data = assert_envelope(get_json("/api/persons/刘备/graph", depth=2), "nodes", "links")
    assert isinstance(data["nodes"], list) and isinstance(data["links"], list), "出图结构不合法"


@check("最短路接口", "P4")
def shortest_path():
    assert_envelope(get_json("/api/path", **{"from": "刘备", "to": "曹操"}), "nodes")


@check("影响力排名接口", "P4")
def pagerank():
    assert_envelope(get_json("/api/stats/pagerank"), "items")


@check("社区发现接口", "P4")
def communities():
    assert_envelope(get_json("/api/stats/communities"), "items")


@check("新增人物后查询", "P2")
def create_and_read():
    payload = {"name": "冒烟测试人物", "faction": "群雄", "role": "测试"}
    resp = requests.post(BASE + "/api/persons", json=payload, timeout=TIMEOUT)
    assert resp.status_code in (200, 201), f"写入失败 HTTP {resp.status_code}"
    found = get_json("/api/persons/冒烟测试人物")
    assert found.status_code == 200, "新增后查不到该人物"


@check("删除人物后查询", "P2")
def delete_and_verify():
    requests.delete(BASE + "/api/persons/冒烟测试人物", timeout=TIMEOUT)
    found = get_json("/api/persons/冒烟测试人物")
    assert found.status_code == 404, "删除后仍能查到该人物"


def main():
    print(f"冒烟检查目标：{BASE}\n")
    failed = 0
    for name, owner, fn in CHECKS:
        try:
            fn()
            print(f"  [通过] {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  [失败] {name}（第一责任人 {owner}）：{exc}")
        except requests.RequestException as exc:
            failed += 1
            print(f"  [失败] {name}（第一责任人 {owner}）：无法连接 {exc}")

    print()
    if failed:
        print(f"冒烟检查未通过：{failed}/{len(CHECKS)} 项失败，禁止合并")
        sys.exit(1)
    print(f"冒烟检查全部通过：{len(CHECKS)}/{len(CHECKS)}")
    sys.exit(0)


if __name__ == "__main__":
    main()
