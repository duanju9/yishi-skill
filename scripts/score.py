#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
奕识 · 证据建模与双分推演
========================
输入：collect_sessions.py 产出的 corpus.json + assets/library.json
输出：report-data.json（可直接注入 assets/report-template.html）

模型：
  Y 轴（底色） 10 维动作倾向，由语料计数经饱和函数映射到 0-100
  X 轴（生态） 岗位需求向量（library.json），适配分 = 岗位看重的维度上你有多接近
  加权层       社会亲缘距离 = 岗位客观开放度 + 语料中该岗位与人脉词的共现修正
  扰动层       焦虑 / 滤镜 / 抗压，只微调权重，不推翻骨架

原则：
  1. 任何分数必须能指回具体证据条数与样本。无数据的维度标"无证据"，不编。
  2. 不写死任何个人偏好。同一份代码跑不同人的语料，结论必须不同。
  3. 决策求助多 → 记为"决策外包倾向"，是负向信号，但只降低置信度，不否定其他维度。
"""

import argparse
import json
import math
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------- 维度映射
# 每个维度由「任务类型计数 + 领域计数」组合，饱和函数压到 0-100

DIM_SOURCES = {
    "analyze": {"tasks": ["分析拆解"], "domains": ["投研财务", "组织管理"], "domain_w": 0.55},
    "build":   {"tasks": ["编码实现"], "domains": ["技术工程"], "domain_w": 0.60},
    "express": {"tasks": ["写作文案"], "domains": ["内容创作"], "domain_w": 0.50},
    "explore": {"tasks": ["信息查询", "学习理解"], "domains": ["ai 应用"], "domain_w": 0.35},
    "decide":  {"tasks": [], "domains": [], "domain_w": 0},          # 反向计算，见下
    "connect": {"tasks": [], "domains": ["人际情感", "组织管理"], "domain_w": 0.80},
    "operate": {"tasks": ["事务操作"], "domains": [], "domain_w": 0},
    "create":  {"tasks": ["创意生成"], "domains": ["内容创作"], "domain_w": 0.40},
    "trade":   {"tasks": [], "domains": ["商业创业"], "domain_w": 0.90},
    "focus":   {"tasks": [], "domains": [], "domain_w": 0},          # 由跨月持续性计算
}

# 岗位与人脉词共现检测（用于社会距离的个人修正）
ROLE_KEYWORDS = {
    "research": r"投研|研究员|行研|券商|基金|买方|卖方|研究所|分析师",
    "content": r"公众号|内容|自媒体|写作|博主|up主|小红书|选题|涨粉",
    "product": r"产品经理|产品岗|pm|需求|原型|prd",
    "consulting": r"咨询|麦肯锡|bcg|贝恩|德勤|埃森哲|case|战略咨询",
    "engineering": r"研发|开发|工程师|后端|前端|算法|技术岗|程序员",
    "strategy": r"战略|战投|商业分析|商分|策略",
    "founder": r"创业|独立开发|自己干|开店|做产品卖|副业",
}
NETWORK_WORDS = r"学长|学姐|前辈|师兄|师姐|校友|内推|mentor|导师|带我的|介绍|认识的人|朋友在|亲戚在|父母|家里人"

# 人物隐含维度（用于匹配）
FIGURE_DIMS = {
    "zengguofan": ["focus", "operate", "analyze"],
    "wangyangming": ["decide", "create", "focus"],
    "zhangjian": ["decide", "trade", "build"],
    "sushi": ["focus", "express", "create"],
    "munger": ["analyze", "explore", "decide"],
    "taleb": ["trade", "decide", "analyze"],
    "duanyongping": ["decide", "trade", "focus"],
    "feynman": ["explore", "express", "analyze"],
    "simaqian": ["focus", "express", "operate"],
}

try:
    from keywords import TASK_TYPES, DOMAINS
except ImportError:  # 作为包被引用时
    from .keywords import TASK_TYPES, DOMAINS

ANXIETY_WORDS = r"焦虑|迷茫|害怕|来不及|同龄人|年龄|慌|压力大|内耗|怀疑自己|没方向|不知道要什么|睡不着"
FILTER_WORDS = r"是不是应该|是不是该|听说|据说|网上说|别人都说|看起来|感觉.*很好|理想|梦想|向往|羡慕"

# 维度证据强度：
#   能力型维度（1.0）—— 委托量能反映练习量与倾向
#   偏好型维度（0.4-0.6）—— 委托量只反映"是否外包给 AI"，是弱证据，不能当硬伤
DIM_WEIGHT = {
    "analyze": 1.0, "build": 1.0, "express": 1.0, "explore": 1.0, "create": 1.0,
    "decide": 0.50, "connect": 0.60, "trade": 0.55, "operate": 0.45, "focus": 0.60,
}


def saturate(x, k=22.0):
    """饱和映射：0→0，k→63，2k→86，3k→95。避免高频者虚高。"""
    if x <= 0:
        return 0
    return round(100 * (1 - math.exp(-x / k)), 1)


def pct(part, total):
    return round(part / max(1, total), 3)


# ---------------------------------------------------------------- 画像

def build_profile(corpus, lib):
    texts = [m["text"] for th in corpus["threads"] for m in th["messages"]]
    n = len(texts)
    tasks = {k: v["count"] for k, v in corpus["stats"].get("task_types", {}).items()}
    doms = corpus["stats"].get("domains", {})
    help_seek = corpus["stats"].get("help_seeking", {})

    dims, trace, known = {}, {}, {}
    for dim, cfg in DIM_SOURCES.items():
        if dim in ("decide", "focus"):
            continue
        task_hits = sum(tasks.get(t, 0) for t in cfg["tasks"])
        dom_hits = sum(doms.get(d, 0) for d in cfg["domains"])
        raw = task_hits + cfg["domain_w"] * dom_hits
        # 用占比而非绝对计数：跨用户可比，避免"说得多的人所有维度满分"
        share = raw / max(1, n)
        dims[dim] = round(100 * (1 - math.exp(-share / 0.15)), 1)
        trace[dim] = {"task_hits": task_hits, "domain_hits": dom_hits,
                      "raw": round(raw, 1), "share": round(share, 3)}
        known[dim] = raw >= 8

    # decide：把决策外包给 AI 的倾向越强，独立决断分越低。
    # 用「决策求助任务占比」为主，「要不要/该不该」表述为辅——后者只是前者的子集。
    ask_ratio = pct(tasks.get("决策求助", 0), n)
    dilemma_ratio = corpus["signals"]["decision_dilemmas"]["ratio"]
    dependence = min(1.0, ask_ratio * 3.0 + dilemma_ratio * 4.0)
    dims["decide"] = round(max(8, 100 - min(70, dependence * 70)), 1)
    trace["decide"] = {"ask_ratio": ask_ratio, "dilemma_ratio": dilemma_ratio,
                       "dependence": round(dependence, 3)}
    known["decide"] = ask_ratio > 0.02

    # focus：跨度越长、活跃月份越多，越说明能长期投入。样本期不足 90 天视为未知。
    span_days = corpus["stats"].get("span_days") or 0
    active_months = [m["month"] for m in corpus["stats"].get("by_month", []) if m["count"] >= 3]
    months = len(active_months)
    dims["focus"] = round(min(100, saturate(span_days, k=120) * 0.75 + min(25, months * 5)), 1)
    trace["focus"] = {"active_months": months, "span_days": span_days}
    known["focus"] = span_days >= 90

    order = lib["dimensions"]
    top = sorted(dims.items(), key=lambda kv: -kv[1])
    weak = sorted(dims.items(), key=lambda kv: kv[1])[:3]

    # 置信度：消息量 + 时间跨度 + 维度覆盖
    covered = len([d for d in dims.values() if d >= 30])
    span_days = span_days or 0
    conf = min(1.0, (min(n, 600) / 600) * 0.5 + (min(span_days, 90) / 90) * 0.3 + (covered / 10) * 0.2)
    if n < 30:
        label = "极低：样本不足 30 条，结论仅作方向参考"
    elif conf < 0.4:
        label = "低：样本偏少或时间跨度短"
    elif conf < 0.7:
        label = "中：可用于排序，但需注意单点证据"
    else:
        label = "较高：样本量与跨度足以支撑结构性判断"

    return {
        "dims": dims,
        "dim_labels": {k: v["label"] for k, v in order.items()},
        "dim_desc": {k: v["desc"] for k, v in order.items()},
        "top": [{"dim": k, "label": order[k]["label"], "score": v} for k, v in top[:4]],
        "weak": [{"dim": k, "label": order[k]["label"], "score": v} for k, v in weak],
        "trace": trace,
        "known": known,
        "confidence": {"score": round(conf, 2), "label": label, "messages": n, "span_days": span_days},
    }


# ---------------------------------------------------------------- 证据

def norm_ts(v):
    """归一化各种时间格式到毫秒时间戳。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        n = float(v)
        if n > 1e14:
            return int(n / 1000)
        if n > 1e11:
            return int(n)
        if n > 1e9:
            return int(n * 1000)
        return None
    s = str(v).strip()
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return norm_ts(float(s))
    try:
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None


def build_timeline(corpus):
    """时序轴：按月统计委托量、主导领域、深度动作占比，并判断连续性。"""
    buckets = {}
    for th in corpus["threads"]:
        for m in th["messages"]:
            ts = norm_ts(m["ts"]) or th["ts_end"]
            if not ts:
                continue
            mon = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m")
            b = buckets.setdefault(mon, {"total": 0, "deep": 0, "doms": {}})
            b["total"] += 1
            for name, pat in TASK_TYPES.items():
                if re.search(pat, m["text"], re.I) and name in ("分析拆解", "写作文案", "编码实现"):
                    b["deep"] += 1
                    break
            for name, pat in DOMAINS.items():
                if re.search(pat, m["text"], re.I):
                    b["doms"][name] = b["doms"].get(name, 0) + 1

    months = sorted(buckets)
    out = []
    for mon in months:
        b = buckets[mon]
        top = max(b["doms"], key=b["doms"].get) if b["doms"] else None
        out.append({
            "month": mon,
            "total": b["total"],
            "top_domain": top,
            "deep_ratio": round(b["deep"] / max(1, b["total"]), 2),
        })

    # 连续性：补全中间断档月份，标出空窗
    if months:
        filled = []
        y, mth = int(months[0][:4]), int(months[0][5:7])
        end_y, end_m = int(months[-1][:4]), int(months[-1][5:7])
        while (y, mth) <= (end_y, end_m):
            key = f"{y:04d}-{mth:02d}"
            rec = next((x for x in out if x["month"] == key), None)
            filled.append(rec or {"month": key, "total": 0, "top_domain": None, "deep_ratio": 0})
            mth += 1
            if mth > 12:
                mth = 1
                y += 1
        out = filled

    gaps = [x["month"] for x in out if x["total"] == 0]
    peak = max(out, key=lambda x: x["total"]) if out else None
    trend = "样本期太短，无法判断趋势"
    if len(out) >= 3:
        first = sum(x["total"] for x in out[:len(out) // 2])
        second = sum(x["total"] for x in out[len(out) // 2:])
        if second > first * 1.25:
            trend = "委托量在上升——你正在加大投入"
        elif second < first * 0.75:
            trend = "委托量在下降——注意力可能转移了，或这段时间没空"
        else:
            trend = "委托量平稳——没有明显的加速或放弃"
    return {"months": out, "gaps": gaps, "peak": peak, "trend": trend,
            "continuity": ("连续，无明显空窗" if not gaps else f"有 {len(gaps)} 个月空窗：{'、'.join(gaps)}")}


def build_evidence(corpus, profile, lib):
    texts = [(m["text"], th["agent"], th["session"], norm_ts(m["ts"]) or th["ts_end"])
             for th in corpus["threads"] for m in th["messages"]]
    tasks = corpus["stats"].get("task_types", {})
    doms = corpus["stats"].get("domains", {})
    total = len(texts)

    def month_postfix(months):
        """把首末月份渲染成'（3–11 月连续）'这类后缀，供证据轴展示时间跨度。"""
        ms = sorted({m for m in months if m})
        if not ms:
            return ""
        if len(ms) == 1:
            return f"（{ms[0]}）"
        return f"（{ms[0]} 至 {ms[-1]}，{len(ms)} 个月）"

    def samples(pattern, k=3):
        out, months = [], []
        for t, agent, sess, ts in texts:
            if re.search(pattern, t, re.I):
                months.append(datetime.fromtimestamp(ts / 1000).strftime("%Y-%m") if ts else None)
                if len(out) < k:
                    out.append({"text": t[:160], "agent": agent, "session": sess})
        return out, months

    gains, losses = [], []

    # 增益：高频委托类型 + 领域
    for name, info in sorted(tasks.items(), key=lambda kv: -kv[1]["count"])[:4]:
        if info["count"] < 5:
            continue
        s, months = samples(task_pattern(name))
        gains.append({
            "title": f"反复委托「{name}」类任务 {info['count']} 次{month_postfix(months)}",
            "detail": f"占全部委托 {round(info['ratio'] * 100)}%。这是你自己主动发起、无人要求的工作，比任何自评都更能说明你愿意把时间花在哪。",
            "dim": map_task_to_dim(name),
            "span": month_postfix(months),
            "samples": s,
        })
    for name, cnt in sorted(doms.items(), key=lambda kv: -(kv[1] or 0))[:3]:
        if cnt < 10:
            continue
        gains.append({
            "title": f"「{name}」相关话题出现 {cnt} 次",
            "detail": "领域级重复，说明这不是一次性好奇，而是持续的关注方向。",
            "dim": name,
            "span": "",
            "samples": [],
        })

    # 损耗：决策外包、反复纠结、焦虑
    d = corpus["signals"]["decision_dilemmas"]
    if d["count"] >= 5:
        losses.append({
            "title": f"两难表述出现 {d['count']} 次（占 {round(d['ratio'] * 100)}%）",
            "detail": "反复在'要不要/该不该'上打转，说明这些决策一直没有被真正做出。纠结本身消耗的精力，往往超过选错。",
            "samples": [{"text": t[:160], "agent": "", "session": ""} for t in d["samples"][:3]],
        })
    anxiety_hits = [t for t, _, _, _ in texts if re.search(ANXIETY_WORDS, t)]
    if len(anxiety_hits) >= 5:
        losses.append({
            "title": f"焦虑类表述 {len(anxiety_hits)} 次",
            "detail": "焦虑期的判断会系统性偏向'尽快确定'。这段时间做出的长期决定，置信度要打折。",
            "samples": [{"text": t[:160], "agent": "", "session": ""} for t in anxiety_hits[:3]],
        })
    if profile["dims"]["decide"] < 45:
        losses.append({
            "title": "决策外包倾向明显",
            "detail": "求助时更常要结论而非要方法。这会让你在做完决策后仍不确定，因为判断标准没有留在自己手上。",
            "samples": [],
        })

    return {"gains": gains, "losses": losses, "dilemmas": d}


def task_pattern(name):
    from_collect = {
        "分析拆解": r"分析|拆解|对比|尽调|调研|评估|复盘|诊断",
        "编码实现": r"写代码|实现|脚本|报错|debug|调试|重构|部署|接口|安装|配置",
        "写作文案": r"写一篇|写份|文案|润色|标题|摘要|公众号|推文|报告|简历",
        "信息查询": r"查一下|搜一下|是什么|有哪些|怎么用|区别|最新|数据",
        "决策求助": r"要不要|该不该|选哪个|怎么办|纠结|建议|推荐|适合我",
        "创意生成": r"点子|创意|想法|头脑风暴|设计一个|策划|取名",
        "学习理解": r"教我|解释|什么意思|原理|入门|怎么学|看懂",
        "事务操作": r"帮我整理|归档|重命名|批量|转成|导出|合并|填表",
    }
    return from_collect.get(name, r".")


def map_task_to_dim(name):
    return {
        "分析拆解": "analyze", "编码实现": "build", "写作文案": "express",
        "信息查询": "explore", "决策求助": "decide", "创意生成": "create",
        "学习理解": "explore", "事务操作": "operate",
    }.get(name, "analyze")


# ---------------------------------------------------------------- 双分推演

def fit_score(user_dims, demand, known=None):
    """岗位看重什么，你就有多接近。

    三层处理，避免把"没让 AI 做过"误判成"做不到"：
      1. 证据不足的维度按中性 55 且权重降到 40%
      2. 偏好型维度（协调/秩序/交易/决断/专注）整体权重打 4-6 折——委托量只反映是否外包
      3. 强项闲废惩罚：岗位不看重（need≤55）而你明显强（≥75），说明这份能力用不上，正是内耗来源
    最后按证据覆盖率向中性 60 收缩，样本越少结论越保守。
    """
    known = known or {}
    num = den = 0.0
    cov_num = cov_den = 0.0
    detail, wasted = [], []
    for dim, need in demand.items():
        u = user_dims.get(dim, 0)
        dw = DIM_WEIGHT.get(dim, 1.0)
        if not known.get(dim, True):
            match, weight, status = 55.0, need * dw * 0.4, "未知"
        else:
            if u < need:
                match, status = 100 - (need - u), "不足"
            else:
                match, status = 100 - (u - need) * 0.55, "充足"
            weight = need * dw
            cov_num += need
            if need <= 55 and u >= 75:
                wasted.append(dim)
        cov_den += need
        num += weight * match
        den += weight
        detail.append({"dim": dim, "you": u, "need": need, "match": round(match, 1),
                       "status": status, "dim_weight": dw})

    raw = num / den if den else 0
    raw -= len(wasted) * 2.5
    coverage = cov_num / cov_den if cov_den else 0
    score = 60 + (raw - 60) * (0.55 + 0.45 * coverage)
    detail.sort(key=lambda x: -x["need"])
    return round(max(0, min(100, score)), 1), detail, wasted, round(coverage, 2)


def social_score(role, corpus):
    """客观开放度 + 语料里该岗位与人脉词的共现修正。"""
    texts = [m["text"] for th in corpus["threads"] for m in th["messages"]]
    kw = ROLE_KEYWORDS.get(role["id"], "")
    cooccur = [t for t in texts if re.search(kw, t, re.I) and re.search(NETWORK_WORDS, t)]
    mentions = [t for t in texts if re.search(kw, t, re.I)]
    bonus = 0
    if cooccur:
        bonus = min(12, 2.0 * len(cooccur))
    confidence = "高" if len(mentions) >= 8 else ("中" if len(mentions) >= 3 else "低")
    value = round(min(100, role["openness"] + bonus), 1)
    return {
        "value": value,
        "objective": role["openness"],
        "bonus": round(bonus, 1),
        "mentions": len(mentions),
        "cooccur": len(cooccur),
        "confidence": confidence,
    }


def quad(fit, social, fit_mid):
    high_fit = fit >= fit_mid
    near = social >= 60
    if high_fit and near:
        return {"key": "best", "label": "最优路线",
                "advice": "做起来顺手，还有人带路，试错成本最低。优先在这里找具体机会，不要因为'不够酷'而跳过。"}
    if high_fit and not near:
        return {"key": "hard", "label": "高潜力高难度",
                "advice": "很适合你，但孤军奋战。信息壁垒和试错成本是主要风险，需要先解决'谁带你进门'，而不是先证明能力。"}
    if not high_fit and near:
        return {"key": "drain", "label": "容易上手但内耗",
                "advice": "路好走，但长期消耗你的底色。短期可做跳板，设一个明确的退出时间点，否则会停在'还行'里。"}
    return {"key": "avoid", "label": "双重劣势",
            "advice": "既不合手也够不着。除非你有非常具体的理由，否则不要把它当主选项。"}


def disturbance(corpus, profile):
    texts = [m["text"] for th in corpus["threads"] for m in th["messages"]]
    n = max(1, len(texts))
    anxiety = round(min(100, len([t for t in texts if re.search(ANXIETY_WORDS, t)]) / n * 300), 1)
    filt = round(min(100, len([t for t in texts if re.search(FILTER_WORDS, t)]) / n * 260), 1)
    span = corpus["stats"].get("span_days") or 0
    resilience = round(min(100, profile["dims"]["focus"] * 0.6 + min(40, span / 3)), 1)
    return {"anxiety": anxiety, "filter": filt, "resilience": resilience}


def build_roles(corpus, lib, profile, dist, confidence=1.0):
    roles = []
    for role in lib["roles"]:
        fit, detail, wasted, coverage = fit_score(profile["dims"], role["demand"], profile.get("known"))
        soc = social_score(role, corpus)
        roles.append({"role": role, "fit": fit, "detail": detail, "social": soc,
                      "wasted": wasted, "coverage": coverage})

    fits = [r["fit"] for r in roles]
    fit_mid = round(statistics.median(fits), 1)

    # 扰动只微调：焦虑高 → 更依赖社会距离；滤镜重 → 对无执行证据的岗位打折
    social_w = 0.45 + (dist["anxiety"] / 100) * 0.12
    out = []
    for r in roles:
        role = r["role"]
        fit = r["fit"]
        penalty = 0.0
        if dist["filter"] >= 55 and r["social"]["confidence"] == "低":
            penalty += dist["filter"] * 0.08
        fit_adj = round(max(0, fit - penalty), 1)
        total = round(fit_adj * (1 - social_w) + r["social"]["value"] * social_w, 1)
        if confidence < 0.30:
            q = {"key": "unknown", "label": "暂不判定",
                 "advice": "样本不足，象限无法可靠划分。此时任何一个标签都是过度解读，建议累积 2-4 周使用记录后重跑。"}
        else:
            q = quad(fit_adj, r["social"]["value"], fit_mid)

        reasons_fit = sorted(r["detail"], key=lambda x: -x["need"])[:3]
        out.append({
            "id": role["id"],
            "name": role["name"],
            "work": role["work"],
            "cost": role["cost"],
            "entry": role["entry"],
            "cycle": role["cycle"],
            "fit": fit_adj,
            "fit_raw": fit,
            "fit_penalty": round(penalty, 1),
            "social": r["social"]["value"],
            "social_detail": r["social"],
            "total": total,
            "quad": q,
            "fit_reasons": reasons_fit,
            "coverage": r["coverage"],
            "wasted": [profile["dim_labels"].get(d, d) for d in r["wasted"]],
            "wasted_note": ("你的「" + "、".join(profile["dim_labels"].get(d, d) for d in r["wasted"]) +
                            "」在这条路上用不上——这是内耗感的直接来源，不是能力问题。") if r["wasted"] else "",
            "scenarios": {
                "optimistic": {"fit": round(min(100, fit_adj + 6), 1), "social": round(min(100, r["social"]["value"] + 9), 1)},
                "base": {"fit": fit_adj, "social": r["social"]["value"]},
                "pessimistic": {"fit": round(max(0, fit_adj - 9), 1), "social": round(max(0, r["social"]["value"] - 11), 1)},
            },
        })

    out.sort(key=lambda x: -x["total"])
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out, fit_mid, round(social_w, 2)


# ---------------------------------------------------------------- 人物与书

def build_figures(lib, profile, evidence, roles):
    dims = profile["dims"]
    dilemma = evidence["dilemmas"]["count"]
    out = []
    for fig in lib["figures"]:
        fdim = FIGURE_DIMS.get(fig["id"], ["analyze"])
        base = sum(dims.get(d, 0) for d in fdim) / len(fdim)
        # 纠结多的人，与"在约束下做取舍"的人物更相关
        bonus = min(8, dilemma * 0.6) if "decide" in fdim else 0
        score = round(min(100, base + bonus), 1)
        out.append({
            "name": fig["name"], "era": fig["era"], "one_line": fig["one_line"],
            "score": score,
            "nodes": fig["nodes"],
            "fit_when": fig["fit_when"],
            "not_comparable": fig["not_comparable"],
            "dims": [profile["dim_labels"].get(d, d) for d in fdim],
        })
    out.sort(key=lambda x: -x["score"])
    return out[:4]


def build_books(lib, profile):
    top_dims = [x["dim"] for x in profile["top"]]
    out = []
    for b in lib["books"]:
        hit = [d for d in b.get("read_now_when", []) if d in top_dims]
        read_now = len(hit) > 0
        out.append({
            "title": b["title"], "author": b["author"],
            "question": b["question"], "answers": b["answers"],
            "why": b["why"], "read_now": read_now,
            "skip_when": b.get("skip_when", ""),
            "hit_dims": [profile["dim_labels"].get(d, d) for d in hit],
            "score": round(60 + 20 * len(hit) + (profile["dims"].get(b["read_now_when"][0], 0) * 0.2 if b.get("read_now_when") else 0), 1),
        })
    out.sort(key=lambda x: (-int(x["read_now"]), -x["score"]))
    return out


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(description="奕识 · 证据建模与双分推演")
    ap.add_argument("--corpus", default="corpus.json")
    ap.add_argument("--lib", default="", help="library.json 路径，默认取脚本同级 ../assets/library.json")
    ap.add_argument("--out", default="report-data.json")
    ap.add_argument("--preset", default="", help="用户心里预设的岗位 id，用于对比定位")
    args = ap.parse_args()

    corpus_path = Path(args.corpus)
    if not corpus_path.is_file():
        raise SystemExit(f"[!] 找不到语料文件：{corpus_path}，请先运行 collect_sessions.py")

    lib_path = Path(args.lib) if args.lib else Path(__file__).resolve().parent.parent / "assets" / "library.json"
    lib = json.loads(lib_path.read_text(encoding="utf-8"))
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))

    if not corpus.get("threads"):
        raise SystemExit("[!] 语料为空，无法建模。请先积累会话记录或导入 ChatGPT 导出。")

    profile = build_profile(corpus, lib)
    timeline = build_timeline(corpus)
    evidence = build_evidence(corpus, profile, lib)
    dist = disturbance(corpus, profile)
    roles, fit_mid, social_w = build_roles(corpus, lib, profile, dist, profile["confidence"]["score"])
    figures = build_figures(lib, profile, evidence, roles)
    books = build_books(lib, profile)

    preset = None
    if args.preset:
        preset = next((r for r in roles if r["id"] == args.preset), None)

    boundaries = [
        {"title": "这里读的是「你委托了什么」，不是「你交付了什么」",
         "detail": "会话记录反映的是你让 AI 做的事，不是你在工作里实际产出的成果。它能证明你的兴趣与思考方向，不能证明你的绩效。"},
        {"title": "社会距离的个人部分依赖共现，样本少时置信度低",
         "detail": "个人资源分是从'岗位关键词 + 人脉词'同句出现的次数推的。没提过不等于没有，提过也不等于能内推。"},
        {"title": "人格倾向不等于胜任力",
         "detail": "拆解欲强不代表能做投研——后者还需要财务基础、承压能力与市场判断。本报告只回答'合不合手'，不回答'够不够格'。"},
        {"title": "扰动层只调权重，不改结论结构",
         "detail": f"当前焦虑 {dist['anxiety']}、滤镜 {dist['filter']}、抗压 {dist['resilience']}，社会距离权重被调到 {social_w}。这些参数会随你的状态变化，骨架不应跟着变。"},
    ]
    if profile["confidence"]["score"] < 0.4:
        boundaries.insert(0, {"title": "样本不足，请把结论当草稿",
                              "detail": f"仅采集到 {profile['confidence']['messages']} 条消息、跨度 {profile['confidence']['span_days']} 天。低于 30 条时任何排序都不可靠。"})

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "meta": corpus.get("meta", {}),
        "stats": corpus.get("stats", {}),
        "profile": profile,
        "evidence": evidence,
        "timeline": timeline,
        "disturbance": dist,
        "weights": {"fit": round(1 - social_w, 2), "social": social_w},
        "fit_mid": fit_mid,
        "roles": roles,
        "preset": preset,
        "figures": figures,
        "books": books,
        "boundaries": boundaries,
    }

    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[✓] 建模完成：{profile['confidence']['messages']} 条委托 / 置信度 {profile['confidence']['score']}")
    print(f"[✓] 底色前四：" + "、".join(f"{t['label']}{t['score']}" for t in profile["top"]))
    print(f"[✓] 权重：适配 {report['weights']['fit']} / 社会距离 {report['weights']['social']}（受焦虑 {dist['anxiety']} 影响）")
    print("[✓] 排序：")
    for r in roles:
        print(f"    {r['rank']}. {r['name']:<16} 适配{r['fit']:>5}  社会{r['social']:>5}  综合{r['total']:>5}  {r['quad']['label']}")
    if preset:
        print(f"[✓] 预设「{preset['name']}」排第 {preset['rank']}，{preset['quad']['label']}")
    print(f"[✓] 输出：{args.out}")


if __name__ == "__main__":
    main()
