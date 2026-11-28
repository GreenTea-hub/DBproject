"""语料切分：把整本《三国演义》按回拆成 120 个文件。负责人：P1。

输入：data/raw/sanguo_full.txt（UTF-8，回目行形如"正文 第一回 宴桃园豪杰三结义 斩黄巾英雄首立功"）
输出：data/raw/chapters/ch001.txt ... ch120.txt，每个文件首行是标准化的"第X回 回目"
      data/build/chapters.csv（回目清单，供后续统计与核对，不入仓库）

设计要点：
1. 幂等：重复执行会覆盖输出目录，不会产生 ch001-1.txt；
2. 校验：切出的回数不是 120 时返回非 0，防止静默产出残缺语料；
3. 保留原文：除回目行外不做任何清洗，正文里的全角空格与换行原样保留。

用法：
    python scripts/split_chapters.py
    python scripts/split_chapters.py --src data/raw/sanguo_full.txt --out data/raw/chapters
"""

import argparse
import csv
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = ROOT / "data" / "raw" / "sanguo_full.txt"
DEFAULT_OUT = ROOT / "data" / "raw" / "chapters"
BUILD_DIR = ROOT / "data" / "build"

# 兼容"第X回"与"正文 第X回"两种写法；标题允许为空
CHAPTER_RE = re.compile(
    r"^[ \t　]*(?:正文[ \t　]*)?第[ \t　]*([一二三四五六七八九十百零〇\d]+)[ \t　]*回[ \t　]*(.*)$",
    re.M,
)
CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def cn_to_int(text):
    """中文数字转整数，支持"一百十八""一百二十"这类省略十的写法。"""
    if text.isdigit():
        return int(text)
    total, section, last = 0, 0, 0
    for ch in text:
        if ch in CN_DIGITS:
            last = CN_DIGITS[ch]
            section = section * 10 + last if section and last == 0 else last
        elif ch == "十":
            section = (section or 1) * 10
            total += section
            section = 0
        elif ch == "百":
            total += (section or 1) * 100
            section = 0
        else:
            raise ValueError(f"无法识别的中文数字：{ch}")
    return total + section


def split(text):
    """返回 [(序号, 标题, 正文)]，序号按出现顺序重排，防止原文编号缺漏。"""
    matches = list(CHAPTER_RE.finditer(text))
    chapters = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[match.end():end]
        body = body.replace("\ufeff", "").strip("\n")
        chapters.append((i + 1, match.group(2).strip(), body))
    return chapters


def main():
    parser = argparse.ArgumentParser(description="按回切分三国演义原文")
    parser.add_argument("--src", default=str(DEFAULT_SRC))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--expect", type=int, default=120, help="期望回数，不符则报错")
    args = parser.parse_args()

    src, out_dir = Path(args.src), Path(args.out)
    if not src.exists():
        sys.exit(f"[错误] 找不到原文：{src}")

    text = src.read_text(encoding="utf-8-sig", errors="ignore")
    chapters = split(text)
    print(f"[1/3] 原文 {len(text)} 字，识别回目 {len(chapters)} 回")

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    rows = []
    for no, title, body in chapters:
        path = out_dir / f"ch{no:03d}.txt"
        path.write_text(f"第{no}回 {title}\n{body}\n", encoding="utf-8")
        rows.append({"no": no, "title": title, "chars": len(body),
                     "paragraphs": body.count("\n") + 1, "file": path.name})

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    manifest = BUILD_DIR / "chapters.csv"
    with manifest.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["no", "title", "chars", "paragraphs", "file"])
        writer.writeheader()
        writer.writerows(rows)

    empties = [r["no"] for r in rows if r["chars"] < 200]
    print(f"[2/3] 已写出 {len(rows)} 个章节文件 → {out_dir}")
    print(f"[3/3] 清单 → {manifest}；正文平均 {sum(r['chars'] for r in rows) // max(len(rows), 1)} 字/回")
    if empties:
        print(f"[警告] 疑似空章节（<200 字）：{empties}")

    if len(chapters) != args.expect:
        sys.exit(f"[错误] 回数 {len(chapters)} 与预期 {args.expect} 不符，请检查原文完整性")

    print("首回：" + rows[0]["title"])
    print("末回：" + rows[-1]["title"])


if __name__ == "__main__":
    main()
