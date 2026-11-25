#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
奕识 · 会话语料采集器
====================
从本机各 AI Agent 的会话记录与记忆文件中，提取"用户委托行为"语料，
输出标准化 JSON，供后续证据建模使用。全程本地读取，不联网、不上传。

支持的来源（自动发现，缺失则跳过）：
  - WorkBuddy     ~/.workbuddy/projects/*/*.jsonl
  - Claude Code   ~/.claude/projects/*/*.jsonl
  - Codex         ~/.codex/sessions/**/*.jsonl, ~/.codex/archived_sessions/*.jsonl
  - Cursor        ~/.cursor/projects/*/**/*.jsonl
  - 记忆文件       ~/.claude/CLAUDE.md, ~/.workbuddy/memory/*.md, ~/.codex/AGENTS.md, 项目内 AGENTS.md/CLAUDE.md
  - ChatGPT 导出   用户指定的 conversations.json（--extra）

用法：
  python collect_sessions.py --out corpus.json
  python collect_sessions.py --out corpus.json --since 90 --agents claude,workbuddy
  python collect_sessions.py --out corpus.json --no-redact --max-per-session 200

设计约束：
  1. 只读，绝不写入或修改任何会话文件。
  2. 默认脱敏：邮箱、手机、身份证、长数字、URL 凭证、密钥、用户目录名。
  3. 默认只保留用户侧消息（role=user），跳过系统注入、工具返回、助手回复。
  4. 单条消息截断到 --max-chars，单会话截断到 --max-per-session，控制体量。
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ---------------------------------------------------------------- 常量

# 各 Agent 的会话根目录（相对 home）
AGENT_ROOTS = {
    "workbuddy": [".workbuddy/projects"],
    "claude": [".claude/projects"],
    "codex": [".codex/sessions", ".codex/archived_sessions"],
    "cursor": [".cursor/projects"],
}

# 记忆文件（相对 home，或项目内）
MEMORY_FILES = [
    ".claude/CLAUDE.md",
    ".codex/AGENTS.md",
    ".workbuddy/memory/MEMORY.md",
]
MEMORY_GLOBS = [
    ".workbuddy/memory/*.md",
    "AGENTS.md",
    "CLAUDE.md",
]

SYSTEM_NOISE = [
    "<system-reminder",
    "<user_info>",
    "<identity_context>",
    "This session is being continued from a previous conversation",
    "Caveat: The messages below were generated",
    "<command-name>",
    "<local-command",
    "[Request interrupted",
]

# 委托行为分类（命中即计分，可多类）
TASK_TYPES = {
    "分析拆解": r"分析|拆解|对比|对比分析|尽职调查|尽调|调研|评估|测算|复盘|拆开|看清|梳理|诊断|归因",
    "编码实现": r"写代码|实现|脚本|函数|报错|debug|调试|重构|部署|接口|爬虫|自动化|正则|sql|python|javascript|安装|配置环境",
    "写作文案": r"写一篇|写份|写个|文案|润色|改稿|标题|摘要|总结成|公众号|推文|邮件|报告|周报|简历",
    "信息查询": r"查一下|搜一下|是什么|怎么回事|多少钱|有哪些|在哪|怎么用|区别|官网|最新|数据",
    "决策求助": r"要不要|该不该|选哪个|哪个好|怎么办|纠结|犹豫|值不值|建议|推荐|适合我|前途|风险",
    "创意生成": r"点子|创意|想法|头脑风暴|设计一个|策划|命名|取名|做个logo|生成图|画",
    "学习理解": r"教我|解释|什么意思|原理|入门|学习路线|怎么学|看懂|通俗|举例",
    "事务操作": r"帮我整理|归档|重命名|批量|转成|转换|导出|导入|格式|合并表格|填表|发邮件|提醒我",
}

# 领域关键词（用于重复主题与禀赋信号）
DOMAINS = {
    "投研财务": r"财报|估值|毛利|营收|净利|现金流|资产负债表|招股|研报|行业|赛道|产业链|竞争格局|市值|pe|pb|dcf|投资|股票|基金|一级市场|fa|并购|上市公司",
    "产品设计": r"产品|需求|prd|原型|交互|用户体验|功能设计|roadmap|产品经理|用户研究|竞品",
    "技术工程": r"代码|架构|接口|数据库|部署|性能|并发|ebpf|内核|网络|协议|运维|前端|后端|算法|开源",
    "内容创作": r"公众号|文章|选题|写作|标题|排版|封面|小红书|短视频|脚本|文案|爆款|ip|粉丝",
    "商业创业": r"商业模式|创业|融资|bp|获客|定价|变现|渠道|私域|增长|客户|销售",
    "职业发展": r"简历|面试|岗位|跳槽|转行|职业|求职|offer|薪资|晋升|工作|公司好",
    "ai 应用": r"agent|大模型|提示词|prompt|llm|rag|微调|智能体|mcp|ai 应用|工作流",
    "组织管理": r"团队|管理|协作|流程|制度|汇报|绩效|招聘|下属|老板|领导",
    "生活习惯": r"健身|睡眠|饮食|健康|旅行|读书|情绪|焦虑|习惯|时间管理",
    "人际情感": r"朋友|家人|父母|关系|沟通|恋爱|社交|同事",
}

STOPWORDS = set(
    "的一个 我们 你们 他们 这个 那个 什么 怎么 可以 是不 不是 有没 没有 就是 如果 然后 还是 "
    "帮我 一下 这个 那个 现在 需要 应该 能不 能不 你这 我要 我想 你能 请问 谢谢 由于 因为 所以 "
    "但是 而且 已经 可能 一些 这样 那样 之后 之前 时候 目前 目前 通过 关于 对于 根据".split()
)


# ---------------------------------------------------------------- 脱敏

def redact(text: str) -> str:
    """脱敏：个人标识、凭证、本地用户名。宁可多打码，不可漏。"""
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "<email>", text)
    text = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "<phone>", text)
    text = re.sub(r"(?<!\d)\d{17}[\dXx](?!\d)", "<id>", text)
    text = re.sub(r"(?<!\d)\d{16,19}(?!\d)", "<card>", text)
    text = re.sub(r"(sk-|ghp_|gho_|xoxb-|AKIA)[A-Za-z0-9_\-]{12,}", "<key>", text)
    text = re.sub(r"([?&](?:token|key|sig|signature|code|access_token|auth)=)[^&\s\"']+", r"\1<redacted>", text, flags=re.I)
    text = re.sub(r"[A-Za-z]:\\Users\\[^\\\s\"']+", r"C:\\Users\\<user>", text)
    text = re.sub(r"/Users/[^/\s\"']+", "/Users/<user>", text)
    text = re.sub(r"/home/[^/\s\"']+", "/home/<user>", text)
    return text


# ---------------------------------------------------------------- 解析

def extract_text(content) -> str:
    """兼容 str / list[block] / dict 三种 content 结构。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        if content.get("type") == "tool_result":
            return ""
        return extract_text(content.get("text") or content.get("content") or "")
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
                continue
            if not isinstance(block, dict):
                continue
            bt = block.get("type", "")
            if bt in ("tool_result", "tool_use", "image", "input_image"):
                continue
            if bt in ("text", "input_text", "output_text") or "text" in block:
                parts.append(str(block.get("text", "")))
        return "\n".join(p for p in parts if p)
    return ""


def is_noise(text: str) -> bool:
    if not text or len(text.strip()) < 2:
        return True
    for marker in SYSTEM_NOISE:
        if marker in text:
            return True
    # 只在原文含标签时才做剥离判断：中文短句（如"要不要转行"）本身是有效消息
    if "<" in text:
        stripped = re.sub(r"<[^>]{0,300}>", "", text).strip()
        if len(stripped) < 4:
            return True
    return False


def parse_jsonl(path: Path, redact_on: bool, max_chars: int):
    """返回 (user_messages, first_ts, last_ts, total_lines)。兼容多种 agent 的落盘格式。"""
    msgs = []
    stamps = []
    total = 0
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                total += 1
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts = obj.get("timestamp") or obj.get("time") or (
                    obj.get("message", {}) or {}
                ).get("timestamp")
                if ts:
                    stamps.append(ts)

                role = obj.get("role") or (obj.get("message", {}) or {}).get("role")
                if role != "user":
                    continue
                if obj.get("type") in ("tool_result", "function_call_result"):
                    continue

                content = obj.get("content")
                if content is None and isinstance(obj.get("message"), dict):
                    content = obj["message"].get("content")
                text = extract_text(content)
                if is_noise(text):
                    continue

                text = re.sub(r"\s+", " ", text).strip()
                if redact_on:
                    text = redact(text)
                if len(text) > max_chars:
                    text = text[:max_chars] + "…"
                msgs.append({"ts": ts, "text": text})
    except (OSError, PermissionError):
        return [], [], [], 0
    return msgs, stamps, total


def norm_ts(v):
    """把各种时间格式归一化成毫秒时间戳。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        n = float(v)
        if n > 1e14:      # 微秒
            return int(n / 1000)
        if n > 1e11:      # 毫秒
            return int(n)
        if n > 1e9:       # 秒
            return int(n * 1000)
        return None
    s = str(v).strip()
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return norm_ts(float(s))
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except ValueError:
        return None


def collect_sessions(home: Path, agents, since_days, redact_on, max_chars, max_per_session):
    cutoff = None
    if since_days and since_days > 0:
        cutoff = int((datetime.now(timezone.utc) - timedelta(days=since_days)).timestamp() * 1000)

    threads = []
    sources = []

    for agent, rel_roots in AGENT_ROOTS.items():
        if agents and agent not in agents:
            continue
        for rel in rel_roots:
            root = home / rel
            if not root.is_dir():
                continue
            files = sorted(root.rglob("*.jsonl"))
            if not files:
                continue
            agent_msgs = 0
            agent_sessions = 0
            for fp in files:
                try:
                    if fp.stat().st_size < 200:      # 空壳文件
                        continue
                except OSError:
                    continue
                msgs, stamps, total_lines = parse_jsonl(fp, redact_on, max_chars)
                if not msgs:
                    continue
                norm = [norm_ts(m["ts"]) for m in msgs] + [norm_ts(s) for s in stamps]
                norm = [t for t in norm if t]
                if cutoff and norm and max(norm) < cutoff:
                    continue
                if cutoff:
                    kept = []
                    for m in msgs:
                        t = norm_ts(m["ts"])
                        if t is None or t >= cutoff:
                            kept.append(m)
                    msgs = kept
                if not msgs:
                    continue
                if max_per_session and len(msgs) > max_per_session:
                    # 保留首尾，中间抽样：开头定调、结尾定结论
                    head = max_per_session // 2
                    tail = max_per_session - head
                    msgs = msgs[:head] + msgs[-tail:]
                threads.append({
                    "agent": agent,
                    "session": fp.stem,
                    "project": fp.parent.name,
                    "ts_start": min(norm) if norm else None,
                    "ts_end": max(norm) if norm else None,
                    "msg_count": len(msgs),
                    "raw_lines": total_lines,
                    "messages": msgs,
                })
                agent_msgs += len(msgs)
                agent_sessions += 1
            if agent_sessions:
                sources.append({"agent": agent, "root": str(root), "sessions": agent_sessions, "messages": agent_msgs})

    return threads, sources


def collect_memory(home: Path, redact_on: bool, max_chars: int = 1200):
    """读取记忆与项目约定文件，作为"用户长期偏好"的补充证据。"""
    found = []
    candidates = [home / p for p in MEMORY_FILES]
    for pattern in MEMORY_GLOBS:
        candidates.extend(sorted(home.glob(pattern))[:5])
    seen = set()
    for fp in candidates:
        try:
            if not fp.is_file() or fp.stat().st_size < 40:
                continue
            key = str(fp.resolve())
            if key in seen:
                continue
            seen.add(key)
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if redact_on:
            text = redact(text)
        found.append({
            "path": str(fp),
            "chars": len(text),
            "excerpt": text[:max_chars],
        })
    return found[:20]


# ---------------------------------------------------------------- 统计

def classify_tasks(texts):
    """每条消息打多标签，返回分类计数与占比。"""
    counts = Counter()
    for t in texts:
        low = t.lower()
        for name, pattern in TASK_TYPES.items():
            if re.search(pattern, low, re.I):
                counts[name] += 1
    total = max(1, len(texts))
    return {k: {"count": v, "ratio": round(v / total, 3)} for k, v in counts.most_common()}


def count_domains(texts):
    counts = Counter()
    for t in texts:
        for name, pattern in DOMAINS.items():
            if re.search(pattern, t, re.I):
                counts[name] += 1
    return dict(counts.most_common())


def recurring_phrases(texts, top_k=40):
    """提取高频 2-4 字片段，用于发现反复出现的自述与纠结点。仅作提示，不作结论。"""
    counter = Counter()
    for t in texts:
        for seg in re.findall(r"[\u4e00-\u9fa5]{2,4}", t):
            if seg in STOPWORDS or len(seg) < 2:
                continue
            if re.search(r"^(的|了|是|在|和|与|就|也|都|很|会|要|我|你|他)", seg):
                continue
            counter[seg] += 1
    return [{"phrase": p, "count": c} for p, c in counter.most_common(top_k) if c >= 3]


def time_profile(threads):
    by_hour = Counter()
    by_month = Counter()
    for th in threads:
        for m in th["messages"]:
            ts = norm_ts(m["ts"]) or th["ts_end"]
            if not ts:
                continue
            dt = datetime.fromtimestamp(ts / 1000)
            by_hour[dt.hour] += 1
            by_month[dt.strftime("%Y-%m")] += 1
    return (
        [{"hour": h, "count": by_hour.get(h, 0)} for h in range(24)],
        [{"month": m, "count": c} for m, c in sorted(by_month.items())],
    )


def decision_signals(texts):
    """决策痕迹：反复出现的两难表述，是纠结点的直接证据。"""
    dilemm = r"要不要|该不该|选哪个|纠结|犹豫|值不值|两条路|取舍|放弃|还是算了|再想想|不确定"
    hits = [t for t in texts if re.search(dilemm, t)]
    return {
        "count": len(hits),
        "ratio": round(len(hits) / max(1, len(texts)), 3),
        "samples": hits[:12],
    }


def help_seeking(texts):
    """求助姿态：要结论 vs 要方法 vs 要执行。"""
    want_answer = r"直接说|给结论|别废话|就说|行不行|到底|一句话|简单说"
    want_method = r"怎么做|如何|步骤|框架|方法|思路|原理|教我"
    want_exec = r"帮我做|帮我写|帮我改|帮我生成|直接给我|你来做|执行|跑一下"
    def ratio(p):
        return round(len([t for t in texts if re.search(p, t, re.I)]) / max(1, len(texts)), 3)
    return {"要结论": ratio(want_answer), "要方法": ratio(want_method), "要执行": ratio(want_exec)}


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(description="奕识 · 会话语料采集器（本地只读）")
    ap.add_argument("--out", default="corpus.json", help="输出 JSON 路径")
    ap.add_argument("--since", type=int, default=180, help="只取最近 N 天，0 表示不限（默认 180）")
    ap.add_argument("--agents", default="", help="只采集指定 agent，逗号分隔：workbuddy,claude,codex,cursor")
    ap.add_argument("--max-chars", type=int, default=400, help="单条消息最大字符（默认 400）")
    ap.add_argument("--max-per-session", type=int, default=120, help="单会话最多保留消息数（默认 120）")
    ap.add_argument("--no-redact", action="store_true", help="关闭脱敏（不建议，输出会含个人标识）")
    ap.add_argument("--home", default="", help="覆盖用户主目录（测试用）")
    ap.add_argument("--extra", default="", help="额外导入 ChatGPT conversations.json 路径")
    args = ap.parse_args()

    home = Path(args.home) if args.home else Path.home()
    agents = [a.strip() for a in args.agents.split(",") if a.strip()] if args.agents else None
    redact_on = not args.no_redact

    threads, sources = collect_sessions(
        home, agents, args.since, redact_on, args.max_chars, args.max_per_session
    )

    # ChatGPT 导出补充
    if args.extra:
        p = Path(args.extra)
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
                n = 0
                for conv in (data if isinstance(data, list) else data.get("conversations", [])):
                    mapping = conv.get("mapping") or {}
                    msgs = []
                    for node in mapping.values():
                        msg = (node or {}).get("message") or {}
                        if msg.get("author", {}).get("role") != "user":
                            continue
                        text = extract_text(msg.get("content"))
                        if is_noise(text):
                            continue
                        text = re.sub(r"\s+", " ", text).strip()
                        if redact_on:
                            text = redact(text)
                        msgs.append({"ts": msg.get("create_time"), "text": text[: args.max_chars]})
                    if msgs:
                        threads.append({
                            "agent": "chatgpt", "session": conv.get("id", f"conv{n}"),
                            "project": "export", "ts_start": None, "ts_end": None,
                            "msg_count": len(msgs), "raw_lines": 0, "messages": msgs,
                        })
                        n += 1
                if n:
                    sources.append({"agent": "chatgpt", "root": str(p), "sessions": n, "messages": sum(t["msg_count"] for t in threads if t["agent"] == "chatgpt")})
                    print(f"[+] ChatGPT 导出导入 {n} 个会话", file=sys.stderr)
            except (json.JSONDecodeError, OSError) as e:
                print(f"[!] ChatGPT 导出解析失败：{e}", file=sys.stderr)

    if not threads:
        print("[!] 未发现任何可读会话。请确认 agent 本机有历史记录，或用 --home 指定目录。", file=sys.stderr)
        out = {
            "meta": {"generated_at": datetime.now(timezone.utc).isoformat(), "sources": [], "redacted": redact_on,
                     "empty": True, "hint": "未发现会话。可用 --extra 导入 ChatGPT 导出，或先正常使用任意 AI Agent 积累记录。"},
            "stats": {"total_messages": 0},
            "threads": [], "memory": [],
        }
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[=] 空结果已写入 {args.out}", file=sys.stderr)
        return

    all_texts = [m["text"] for th in threads for m in th["messages"]]
    by_hour, by_month = time_profile(threads)
    span_days = None
    stamps = [t for th in threads for t in (th["ts_start"], th["ts_end"]) if t]
    if stamps:
        span_days = round((max(stamps) - min(stamps)) / 86400000, 1)

    corpus = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "redacted": redact_on,
            "since_days": args.since,
            "home": str(home),
            "sources": sources,
            "note": "仅采集用户委托行为（role=user），已过滤系统注入与工具返回。数据未离开本机。",
        },
        "stats": {
            "total_threads": len(threads),
            "total_messages": len(all_texts),
            "span_days": span_days,
            "avg_chars": round(sum(len(t) for t in all_texts) / max(1, len(all_texts)), 1),
            "by_agent": dict(Counter(th["agent"] for th in threads)),
            "by_hour": by_hour,
            "by_month": by_month,
            "task_types": classify_tasks(all_texts),
            "domains": count_domains(all_texts),
            "help_seeking": help_seeking(all_texts),
            "recurring_phrases": recurring_phrases(all_texts),
        },
        "signals": {
            "decision_dilemmas": decision_signals(all_texts),
        },
        "threads": threads,
        "memory": collect_memory(home, redact_on),
    }

    Path(args.out).write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[✓] 采集完成：{len(threads)} 个会话 / {len(all_texts)} 条用户消息 / 跨度 {span_days} 天")
    print(f"[✓] 来源：" + "、".join(f"{s['agent']}({s['sessions']}会话)" for s in sources))
    print(f"[✓] 脱敏：{'开启' if redact_on else '关闭'}　输出：{args.out}")
    top_tasks = list(corpus["stats"]["task_types"].items())[:3]
    if top_tasks:
        print("[✓] 委托类型前三：" + "、".join(f"{k}({v['count']})" for k, v in top_tasks))
    top_dom = list(corpus["stats"]["domains"].items())[:3]
    if top_dom:
        print("[✓] 领域前 三：" + "、".join(f"{k}({v})" for k, v in top_dom))


if __name__ == "__main__":
    main()
