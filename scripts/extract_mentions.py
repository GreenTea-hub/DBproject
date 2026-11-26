"""文本抽取与共现统计。负责人：P1。

功能：
1. 把 data/raw/ 下的一百二十回原文按"第 X 回"切分成章节；
2. 用 data/persons.csv 里的姓名与别名做词典匹配，统计每回的人物出现次数；
3. 统计同回共现的人物对，输出 data/build/cooccurrence.csv（供人工标注关系类型）；
4. --validate：校验 data/*.csv 的列名、枚举、外键、重复边与孤立点。

用法：
    python scripts/extract_mentions.py                 # 抽取 + 共现统计
    python scripts/extract_mentions.py --validate      # 只跑数据质检
    python scripts/extract_mentions.py --top 30        # 只看共现最高的 30 对

注意：抽取结果只是"候选关系"，type / evidence / confidence 必须人工标注后才算数。
"""

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
BUILD_DIR = ROOT / "data" / "build"
PERSONS_CSV = ROOT / "data" / "persons.csv"
RELATIONS_CSV = ROOT / "data" / "relations.csv"
EVENTS_CSV = ROOT / "data" / "events.csv"
FACTIONS_CSV = ROOT / "data" / "factions.csv"

CHAPTER_RE = re.compile(r"^\s*第\s*([一二三四五六七八九十百零〇\d]+)\s*回[ 　]*(.*)$", re.M)
RELATION_TYPES = {"君臣", "兄弟", "敌对", "亲族", "师徒", "同僚"}
FACTIONS = {"魏", "蜀", "吴", "群雄"}

PERSON_COLUMNS = ["name", "aliases", "faction", "role", "gender", "birth_year", "death_year"]
RELATION_COLUMNS = ["source", "target", "type", "weight", "evidence", "confidence"]
EVENT_COLUMNS = ["name", "year", "chapter", "result", "place", "participants"]


# ---------------------------------------------------------------- 词典

def load_persons(path=PERSONS_CSV):
    """返回 [{"name":..., "aliases":[...], ...}]；文件不存在时给出明确提示。"""
    if not path.exists():
        sys.exit(f"[错误] 找不到人物词典：{path}")
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            row = {k: (v or "").strip() for k, v in row.items()}
            aliases = [a for a in re.split(r"[|，,、]", row["aliases"]) if a]
            rows.append({**row, "aliases": aliases})
    return rows


def build_alias_index(persons):
    """别名 -> 主名。长名优先匹配，避免"刘"抢走"刘玄德"。"""
    index = {}
    for p in persons:
        for alias in [p["name"], *p["aliases"]]:
            index.setdefault(alias, p["name"])
    return dict(sorted(index.items(), key=lambda kv: len(kv[0]), reverse=True))


# ---------------------------------------------------------------- 章节切分

def iter_chapters(raw_dir=RAW_DIR):
    """按"第 X 回"切分 raw 目录下所有 txt。返回 (回目号, 标题, 正文) 列表。"""
    if not raw_dir.exists():
        sys.exit(f"[错误] 找不到原文目录：{raw_dir}（原始语料不入仓库，请从群共享目录拷入）")

    files = sorted(raw_dir.glob("*.txt"))
    if not files:
        sys.exit(f"[错误] {raw_dir} 下没有 .txt 原文")

    chapters = []
    for file in files:
        text = file.read_text(encoding="utf-8", errors="ignore")
        matches = list(CHAPTER_RE.finditer(text))
        if not matches:
            print(f"[警告] {file.name} 未匹配到回目，已跳过")
            continue
        for i, match in enumerate(matches):
            title_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[match.end():title_end].strip()
            chapters.append((len(chapters) + 1, match.group(2).strip(), body))
    return chapters


# ---------------------------------------------------------------- 统计

def count_mentions(chapters, alias_index):
    """回目 -> Counter(主名 -> 出现次数)。"""
    per_chapter = {}
    for no, _title, body in chapters:
        counter = Counter()
        for alias, name in alias_index.items():
            hits = body.count(alias)
            if hits:
                counter[name] += hits
        per_chapter[no] = counter
    return per_chapter


def cooccurrence(per_chapter, min_chapters=1):
    """同回共现：人物对 -> (共现回数, 原始次数)。"""
    pairs = defaultdict(lambda: {"chapters": 0, "count": 0, "where": []})
    for no, counter in per_chapter.items():
        names = [n for n, c in counter.items() if c > 0]
        for a, b in combinations(sorted(names), 2):
            item = pairs[(a, b)]
            item["chapters"] += 1
            item["count"] += min(counter[a], counter[b])
            item["where"].append(no)
    return {k: v for k, v in pairs.items() if v["chapters"] >= min_chapters}


def normalize_weight(pairs):
    """把共现次数压到 1—100，最大者取 100。"""
    if not pairs:
        return
    peak = max(v["count"] for v in pairs.values()) or 1
    for v in pairs.values():
        v["weight"] = max(1, round(v["count"] * 100 / peak))


def write_cooccurrence(pairs, out_path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(pairs.items(), key=lambda kv: kv[1]["count"], reverse=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["source", "target", "chapters", "count", "weight", "evidence"])
        for (a, b), v in ordered:
            where = "、".join(f"第{n}回" for n in sorted(v["where"])[:5])
            writer.writerow([a, b, v["chapters"], v["count"], v.get("weight", 1),
                             f"同回共现：{where}"])
    return ordered


# ---------------------------------------------------------------- 质检

def _read_csv(path, expected_columns):
    if not path.exists():
        return None, [f"缺少文件：{path.name}"]
    errors = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header = [h.strip() for h in (reader.fieldnames or [])]
        if header != expected_columns:
            errors.append(f"{path.name} 列名不符：期望 {expected_columns}，实际 {header}")
        rows = [{k.strip(): (v or "").strip() for k, v in row.items()} for row in reader]
    return rows, errors


def validate():
    """数据质检：列名、枚举、外键、重复边、自环、孤立点。"""
    problems = []

    persons, errs = _read_csv(PERSONS_CSV, PERSON_COLUMNS)
    problems += errs
    factions, errs = _read_csv(FACTIONS_CSV, ["name", "color"])
    problems += errs
    relations, errs = _read_csv(RELATIONS_CSV, RELATION_COLUMNS)
    problems += errs
    events, errs = _read_csv(EVENTS_CSV, EVENT_COLUMNS)
    problems += errs

    if persons is None or relations is None:
        _report(problems)
        return 1

    names = {p["name"] for p in persons}
    if len(names) != len(persons):
        problems.append("persons.csv 存在重名人物")

    for p in persons:
        if p["faction"] and p["faction"] not in FACTIONS:
            problems.append(f"人物 {p['name']} 的阵营非法：{p['faction']}")

    seen = set()
    for r in relations:
        if r["source"] not in names:
            problems.append(f"关系起点不在词典中：{r['source']}")
        if r["target"] not in names:
            problems.append(f"关系终点不在词典中：{r['target']}")
        if r["type"] not in RELATION_TYPES:
            problems.append(f"关系类型非法：{r['source']}-{r['target']} = {r['type']}")
        if r["source"] == r["target"]:
            problems.append(f"自环关系：{r['source']}")
        key = tuple(sorted((r["source"], r["target"])))
        if key in seen:
            problems.append(f"重复边（同一对人出现两次）：{r['source']}-{r['target']}")
        seen.add(key)
        try:
            weight = int(r["weight"])
            if not 1 <= weight <= 100:
                problems.append(f"weight 越界：{r['source']}-{r['target']} = {weight}")
        except ValueError:
            problems.append(f"weight 不是整数：{r['source']}-{r['target']}")
        try:
            conf = float(r["confidence"])
            if not 0 <= conf <= 1:
                problems.append(f"confidence 越界：{r['source']}-{r['target']} = {conf}")
        except ValueError:
            problems.append(f"confidence 不是小数：{r['source']}-{r['target']}")

    connected = set()
    for r in relations:
        connected.add(r["source"])
        connected.add(r["target"])
    isolated = sorted(names - connected)
    if isolated:
        problems.append(f"孤立人物（无任何关系）{len(isolated)} 人：" + "、".join(isolated[:10]))

    if events:
        for e in events:
            if not e["name"]:
                problems.append("event 存在空名字")
            if e["chapter"] and not e["chapter"].isdigit():
                problems.append(f"事件 {e['name']} 的 chapter 不是数字")
            for item in (e["participants"] or "").split("|"):
                if not item:
                    continue
                person = item.split(":")[0]
                if person not in names:
                    problems.append(f"事件 {e['name']} 的参与者不在词典中：{person}")

    _report(problems)
    return 1 if problems else 0


def _report(problems):
    if not problems:
        print("[质检通过] 列名、枚举、外键、重复边、孤立点均未发现问题")
        return
    print(f"[质检发现 {len(problems)} 个问题]")
    for item in problems:
        print("  -", item)


# ---------------------------------------------------------------- 主流程

def main():
    parser = argparse.ArgumentParser(description="三国语料抽取与共现统计")
    parser.add_argument("--validate", action="store_true", help="只做数据质检")
    parser.add_argument("--top", type=int, default=20, help="打印共现最高的 N 对")
    parser.add_argument("--min-chapters", type=int, default=1, help="至少共现几回才保留")
    parser.add_argument("--out", default=str(BUILD_DIR / "cooccurrence.csv"))
    args = parser.parse_args()

    if args.validate:
        sys.exit(validate())

    persons = load_persons()
    alias_index = build_alias_index(persons)
    chapters = iter_chapters()
    print(f"[1/4] 切分回目：{len(chapters)} 回（预期 120 回）")
    if len(chapters) < 100:
        print("[警告] 回目数偏少，检查原文是否完整")

    per_chapter = count_mentions(chapters, alias_index)
    total_mentions = sum(sum(c.values()) for c in per_chapter.values())
    print(f"[2/4] 词典人物 {len(persons)} 人，命中 {sum(1 for c in per_chapter.values() if c)} 回，"
          f"提及合计 {total_mentions} 次")

    pairs = cooccurrence(per_chapter, args.min_chapters)
    normalize_weight(pairs)
    print(f"[3/4] 共现人物对：{len(pairs)} 对")

    ordered = write_cooccurrence(pairs, Path(args.out))
    print(f"[4/4] 已写出：{args.out}")

    print(f"\n共现最高的 {args.top} 对（候选关系，需人工标注 type / evidence / confidence）：")
    for (a, b), v in ordered[: args.top]:
        print(f"  {a} — {b}：共现 {v['chapters']} 回，次数 {v['count']}，权重 {v.get('weight')}")


if __name__ == "__main__":
    main()
