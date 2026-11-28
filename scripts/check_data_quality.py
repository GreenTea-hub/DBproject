"""数据质检：证据回原文核对。负责人：P1。

`extract_mentions.py --validate` 只查格式（列名、枚举、外键、重复边、孤立点），
本脚本查内容，回答答辩最容易被问的两件事：

1. relations.csv 里写的那条 evidence，回目号对不对？回目名是不是那一回的？
   两个人物是不是真的在这一回同时出现？
2. 人工标注的 weight 和原文共现强度是否一致？差得多的挑出来复核。

判定口径：
- 错误：回目号越界、回目名与该回不符、起点或终点在该回一次都没出现；
- 提醒：evidence 未按"第X回"开头（无法自动核对，需人工抽检）、权重与共现排序明显背离。

用法：
    python scripts/check_data_quality.py
    python scripts/check_data_quality.py --strict    # 有提醒也返回非 0
"""

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_mentions import (  # noqa: E402
    RELATIONS_CSV, BUILD_DIR, build_alias_index, iter_chapters, load_persons,
)

CHAPTER_NO_RE = re.compile(r"第\s*(\d+)\s*回")


def norm(text):
    """抹掉全角/半角空格差异，便于比对回目名。"""
    return re.sub(r"[\s　]+", "", text or "")


def show_sample(relations, titles, bodies, idx, n, seed):
    """随机抽 n 条边，把该回里两人同现的原句打出来，供人工判断情节描述是否属实。"""
    import random
    pool = [r for r in relations if "推定" not in r["evidence"] and "同阵营共现" not in r["evidence"]]
    random.seed(seed)
    for r in random.sample(pool, min(n, len(pool))):
        m = CHAPTER_NO_RE.search(r["evidence"])
        if not m:
            continue
        no = int(m.group(1))
        body = bodies.get(no, "")
        sentence = ""
        for s in re.split(r"(?<=[。！？])", body):
            if (any(a in s for a, nm in idx.items() if nm == r["source"])
                    and any(a in s for a, nm in idx.items() if nm == r["target"])):
                sentence = s.strip()[:110]
                break
        print(f"[{r['source']}-{r['target']}] {r['type']} weight={r['weight']} "
              f"confidence={r['confidence']}")
        print(f"  标注：{r['evidence']}")
        print(f"  原文：{sentence or '（本回未见同句，两人分开出现）'}")
        print()


def main():
    parser = argparse.ArgumentParser(description="关系证据回原文核对")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--sample", type=int, default=0, help="额外随机抽 N 条边打印原文语境")
    parser.add_argument("--seed", type=int, default=20261126)
    args = parser.parse_args()

    persons = load_persons()
    idx = build_alias_index(persons)
    chapters = iter_chapters()
    titles = {no: title for no, title, _ in chapters}
    bodies = {no: body for no, _t, body in chapters}

    with RELATIONS_CSV.open(encoding="utf-8-sig", newline="") as f:
        relations = list(csv.DictReader(f))

    errors, warns = [], []
    for r in relations:
        ev = (r["evidence"] or "").strip()
        m = CHAPTER_NO_RE.search(ev)
        tag = f"{r['source']}-{r['target']}"
        inferred = "归属推定" in ev
        if not m:
            warns.append(f"{tag}：evidence 未以“第X回”开头，需人工抽检 -> {ev}")
            continue
        no = int(m.group(1))
        if no not in titles:
            errors.append(f"{tag}：回目号 {no} 不存在")
            continue
        # 回目名核对：evidence 里写的标题片段必须出现在真实回目中
        claim = norm(ev[m.end():].split("（")[0])
        if claim and claim not in norm(titles[no]):
            errors.append(f"{tag}：第{no}回回目名不符，标注“{claim}”，实为“{titles[no].strip()}”")
        # 同回出现核对
        body = bodies[no]
        present = {role: any(a in body for a, n in idx.items() if n == r[role])
                   for role in ("source", "target")}
        if inferred:
            # 归属推定的证据只声明"此人第X回首次出场"，不要求主同回在场
            if not any(present.values()):
                errors.append(f"{tag}：推定边在第{no}回未找到任何一方，回目号有误")
        else:
            for role in ("source", "target"):
                if not present[role]:
                    errors.append(f"{tag}：{r[role]} 在第{no}回正文中未出现（该回不支撑此关系）")

    # 权重与共现强度比对
    cooc = {}
    cooc_path = BUILD_DIR / "cooccurrence.csv"
    if cooc_path.exists():
        with cooc_path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                cooc[tuple(sorted((row["source"], row["target"])))] = int(row["weight"])

        # 只用事件级人工标注边算一致性：推定边与同僚补边的权重本身就取自共现
        manual_only = [r for r in relations
                       if "归属推定" not in r["evidence"] and "同阵营共现" not in r["evidence"]]
        both = [(int(r["weight"]), cooc[tuple(sorted((r["source"], r["target"])))], r)
                for r in manual_only if tuple(sorted((r["source"], r["target"]))) in cooc]
        if len(both) > 2:
            def rank(values):
                order = sorted(range(len(values)), key=lambda i: values[i])
                out = [0] * len(values)
                for pos, i in enumerate(order):
                    out[i] = pos
                return out
            a, b = rank([x[0] for x in both]), rank([x[1] for x in both])
            n = len(both)
            mean = (n - 1) / 2
            num = sum((x - mean) * (y - mean) for x, y in zip(a, b))
            den = (sum((x - mean) ** 2 for x in a) * sum((y - mean) ** 2 for y in b)) ** 0.5
            rho = num / den if den else 0
            print(f"事件级标注权重与共现权重 Spearman ρ = {rho:.2f}（{n} 对可比）")
            for manual, auto, r in both:
                if manual >= 75 and auto <= 10:
                    warns.append(f"{r['source']}-{r['target']}：人工权重 {manual} 高，"
                                 f"但共现仅 {auto}，建议复核证据")
                elif manual <= 35 and auto >= 70:
                    warns.append(f"{r['source']}-{r['target']}：共现 {auto} 很强，"
                                 f"人工权重仅 {manual}，建议复核")

    total = max(len(relations), 1)
    inferred = sum(1 for r in relations if "归属推定" in r["evidence"])
    peer = sum(1 for r in relations if "同阵营共现" in r["evidence"])
    manual = total - inferred - peer
    print(f"关系 {total} 条：事件级标注 {manual} 条（{manual * 100 // total}%），"
          f"归属推定 {inferred} 条（{inferred * 100 // total}%），"
          f"同僚补边 {peer} 条（{peer * 100 // total}%）")
    print(f"回目核对：错误 {len(errors)}，提醒 {len(warns)}")
    for item in errors[:30]:
        print("  [错误]", item)
    for item in warns[:15]:
        print("  [提醒]", item)
    if len(warns) > 15:
        print(f"  …… 另有 {len(warns) - 15} 条提醒未列出")

    if args.sample:
        print(f"\n===== 随机抽检 {args.sample} 条（seed={args.seed}）=====")
        show_sample(relations, titles, bodies, idx, args.sample, args.seed)

    if errors:
        return 1
    return 1 if (warns and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
