#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
奕识 · 报告渲染器
================
把 report-data.json 注入 assets/report-template.html，产出可直接双击打开的单文件报告。
不依赖网络、不依赖构建工具。

用法：
  python render.py --data report-data.json --out 奕识报告.html
  python render.py --data report-data.json --out ./report.html --title "李四的职业决策报告"
"""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description="奕识 · 报告渲染器")
    ap.add_argument("--data", default="report-data.json")
    ap.add_argument("--template", default="", help="默认取脚本同级 ../assets/report-template.html")
    ap.add_argument("--out", default="奕识报告.html")
    ap.add_argument("--title", default="", help="覆盖报告标题")
    args = ap.parse_args()

    data_path = Path(args.data)
    if not data_path.is_file():
        raise SystemExit(f"[!] 找不到数据文件：{data_path}，请先运行 score.py")

    tmpl_path = Path(args.template) if args.template else (
        Path(__file__).resolve().parent.parent / "assets" / "report-template.html"
    )
    if not tmpl_path.is_file():
        raise SystemExit(f"[!] 找不到模板：{tmpl_path}")

    data = json.loads(data_path.read_text(encoding="utf-8"))
    html = tmpl_path.read_text(encoding="utf-8")

    payload = json.dumps(data, ensure_ascii=False)
    # 防止 JSON 内容提前闭合 script 标签，并处理 JS 里的行分隔符
    payload = payload.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")

    marker = "/*__YISHI_DATA__*/ null"
    if marker not in html:
        raise SystemExit("[!] 模板缺少数据占位符 /*__YISHI_DATA__*/ null，请检查模板版本")
    html = html.replace(marker, payload, 1)

    if args.title:
        html = re.sub(r"<title>[^<]*</title>", f"<title>{args.title}</title>", html, count=1)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    size_kb = out_path.stat().st_size / 1024
    print(f"[✓] 报告已生成：{out_path}（{size_kb:.0f} KB，单文件，可直接双击打开）")
    top = data.get("roles", [])[:3]
    if top:
        print("[✓] 排名前三：" + "、".join(f"{r['name']}({r['total']})" for r in top))
    conf = data.get("profile", {}).get("confidence", {})
    if conf.get("score", 1) < 0.4:
        print("[!] 置信度偏低，报告已自动在首屏标注边界，请勿直接据此做长期决定")


if __name__ == "__main__":
    main()
