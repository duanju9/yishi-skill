# 奕识 · 三维决策系统

> 不问你说自己是谁，只读你实际做过什么。

[![License: MIT](https://img.shields.io/badge/License-MIT-2E6FD6.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-0F8A72.svg)](https://www.python.org/)
[![No dependencies](https://img.shields.io/badge/dependencies-none-B87B15.svg)](#)
[![No network](https://img.shields.io/badge/data-never%20leaves%20your%20machine-C0392B.svg)](#隐私)

一个 Claude Code / WorkBuddy / Cursor 通用的 skill：读取你本机已有的 AI 会话与记忆，还原真实行为证据，算出你与 7 条职业路径的**加权适配排序**，并生成一份可以直接打开的可视化报告。

**三步开始**：复制下面这段 → 粘给任意能跑命令的 AI → 它会自己装、自己采集、自己出报告。

```
请安装并使用「奕识决策」skill，仓库：https://github.com/duanju9/yishi-skill

1. 克隆到你的 skills 目录：Claude Code 用 ~/.claude/skills/yishi-skill，
   WorkBuddy 用 ~/.workbuddy/skills/yishi-skill，其他环境放任意本地目录。
2. 读取该目录的 SKILL.md，严格按其中 5 步工作流执行，不要自创流程。
3. 采集后把「会话数 / 消息数 / 时间跨度 / 委托类型前三 / 领域前三」念给我确认。
4. 建模前先问我心里有没有预设方向。
5. 出报告后用文字讲：最强证据、最反直觉的发现、我的预设排第几、三条边界。

硬性约束：不要跳过采集自己编分数；全程本地不上传；少于 30 条消息就直接说样本不足。
```

不想装 skill 也行——`git clone` 后跑三条 python 命令即可，见下方「安装」里的第三种方式。

## 它解决什么问题

所有职业测评都在问"你是什么样的人"。但自述会撒谎——尤其是在焦虑、在羡慕别人的时候。

这个工具换了个入口：**你反复让 AI 帮你做什么，比你怎么描述自己更诚实。** 没人会连续三个月委托自己讨厌的事。

## 输出长什么样

跑完会得到一份单文件 HTML（约 70 KB，离线可看），固定七节，顶部有锚点导航：

| 节 | 内容 |
|---|---|
| ① 证据轴 | 每月委托量轨迹图、连续性与趋势判断、增益 / 损耗动作清单（带次数、占比、脱敏样本） |
| ② 底色轴 | 10 维动作倾向雷达图与明细，证据不足的维度灰显为"未知" |
| ③ 岗位排序 | 7 条路径的综合排序，点开看适配理由、社会距离、长期隐性消耗、三情景推演 |
| ④ 四象限 | 适配 × 社会距离散点图，四个象限各有哪几个岗位、分别意味着什么 |
| ⑤ 历史人物 | 4 位人物的决策节点指纹（约束 / 可选 / 放弃 / 守住 / 代价），附"不能类比之处" |
| ⑥ 书籍匹配 | 12 本按"回答什么决策问题"索引，分"现在读"与"现在不必读" |
| ⑦ 扰动校准 | 拖动焦虑 / 滤镜 / 抗压滑块，实时看排序怎么变、骨架稳不稳 |
| 附 | 这份报告不能回答什么 |

真实样本（801 条委托、45 天、87 个会话）：

```
1. 财经内容 / 独立研究   适配 83.7  社会 86  综合 84.7  最优路线
2. 产品经理            适配 81.1  社会 82  综合 81.5  容易上手但内耗
3. 独立开发 / 创业       适配 78.2  社会 75  综合 76.7  容易上手但内耗
4. 战略 / 商业分析       适配 88.1  社会 61  综合 75.7  最优路线
5. 产业研究 / 投研       适配 83.7  社会 66  综合 75.6  最优路线
6. 技术研发 / AI 应用    适配 74.0  社会 73  综合 73.5  容易上手但内耗
7. 管理咨询            适配 86.1  社会 41  综合 65.5  高潜力高难度

预设「产品经理」排第 2 —— 容易上手但内耗
原因：拆解分析（你 85 / 岗位需 55）在这条路上用不上
```

## 安装

### 方式一：复制一段话，让 AI 自己装自己跑（最省事）

把下面**整段**粘给 Claude Code / Cursor / WorkBuddy / 任何能执行命令的 AI：

```
请安装并使用「奕识决策」skill，仓库：https://github.com/duanju9/yishi-skill

1. 克隆到你的 skills 目录（按你的环境选一个，不存在就创建）：
   Claude Code   → ~/.claude/skills/yishi-skill
   WorkBuddy     → ~/.workbuddy/skills/yishi-skill
   Cursor        → ~/.cursor/skills/yishi-skill
   其他          → 任意本地目录也可，后续按绝对路径调用脚本

2. 读取该目录下的 SKILL.md，严格按里面的 5 步工作流执行，不要自创流程。

3. 第 1 步采集时，把终端输出的「会话数 / 消息数 / 时间跨度 / 委托类型前三 / 领域前三」
   念给我确认，再继续。

4. 建模前先问我：心里有没有预设方向（产品 / 咨询 / 投研 / 内容 / 技术 / 战略 / 创业）。

5. 生成报告 HTML 后，用文字讲四件事：最强的证据是哪条、最反直觉的发现是什么、
   我的预设排第几、这份报告的三条边界。

硬性约束：
- 不要跳过采集步骤自己编分数，所有分数必须由我的语料算出来。
- 全程本地读取、本地生成，不要上传我的任何数据，不要索取账号密码。
- 如果采集到的消息少于 30 条，直接告诉我"样本不足"，不要硬出结论。
```

### 方式二：一行命令装好，然后说一句话

macOS / Linux / Git Bash：

```bash
git clone --depth 1 https://github.com/duanju9/yishi-skill.git ~/.claude/skills/yishi-skill
```

Windows PowerShell：

```powershell
git clone --depth 1 https://github.com/duanju9/yishi-skill.git "$env:USERPROFILE\.workbuddy\skills\yishi-skill"
```

装完直接说：**"用奕识分析我该做什么方向"**。

### 方式三：不装 skill，直接跑脚本

```bash
git clone --depth 1 https://github.com/duanju9/yishi-skill.git /tmp/yishi-skill
cd /tmp/yishi-skill

# 1. 采集（默认最近 180 天，自动脱敏）
python scripts/collect_sessions.py --out corpus.json --since 180

# 2. 建模（--preset 填你心里的预设：research/content/product/consulting/engineering/strategy/founder）
python scripts/score.py --corpus corpus.json --out report-data.json --preset product

# 3. 渲染（产出单文件 HTML，双击即开）
python scripts/render.py --data report-data.json --out 我的决策报告.html
```

只依赖 Python 3.9+ 标准库，不需要 pip 安装任何东西。三条命令、两分钟。

### 拿不到 GitHub 时

网络受限的话，任意镜像前缀都能用，例如：

```bash
git clone --depth 1 https://ghproxy.net/https://github.com/duanju9/yishi-skill.git
```

或者直接把仓库页面打包下载解压，效果一样。

## 只有手机？三个版本，按环境选

| 版本 | 需要什么 | 数据来源 | 精度 |
|---|---|---|---|
| **脚本完整版** | 电脑 + Python 3.9+ | 半年本机 AI 会话记录 | 高，每条结论可追溯到条数 |
| **现场取证版** | 手机浏览器，点开即用<br>[duanju9.github.io/yishi-skill](https://duanju9.github.io/yishi-skill/) | 18 次限时两难取舍 | 中，能定方向 |
| **纯提示词版** | 一段话，粘给任意 AI | agent 自己能读到的：对话、记忆、文档、会议记录 | 中低，依赖 agent 自觉 |

**只有手机、连网页都不想开**的时候用第三个。复制下面这段：

```
你做一次职业方向分析，但不能运行任何脚本，只能用手上能访问到的信息。

第一步：盘点数据源。列出你能读到的关于我的东西——本次对话、长期记忆、
文档笔记、邮件、会议记录与转录——逐条标来源和时间范围。拿不到的直说。

第二步：等我确认再继续。

第三步：只从"我做过的事"里取证据。不要用我的自我描述（"我觉得我适合X"），
只找我实际提的请求、做的动作、反复纠结的问题。每条引用原话并标时间。

第四步：十个维度（拆解/建构/表达/探究/决断/协调/秩序/创造/交易/专注）
只给四档：高 / 中 / 低 / 无证据。不要给 0-100 分数，你无法精确。
每条判断必须挂一条原话证据，没有就写"无证据"。

第五步：七条路径（投研/内容/产品/咨询/技术/战略/创业）各给：
适配高中低 + 理由、社会距离近中远 + 依据、四象限归属、长期隐性消耗。最后排序。

第六步：按七节输出——①证据 ②底色 ③岗位排序 ④四象限（文字说明，不画图）
⑤历史人物（比决策结构，每位写"不能类比之处"）⑥书籍（现在读3本+现在别读2本）
⑦校准（我的焦虑/滤镜/抗压怎么影响结论）

硬性规则：
· 任何结论必须能指回具体证据，指不回去的删掉
· 不许编造我说过的话
· 数据不足就明说"样本不足"，不要用漂亮话掩盖
· 只回答"合不合手、够不够得着"，不回答"我该选哪个"
```

完整的移动端流程、数据源盘点技巧、四个常见故障见 [`mobile-prompt.md`](mobile-prompt.md)。

## 分享给别人

把仓库下载到本地，双击 `share.html`，里有三个版本可一键复制：完整提示词、分享文案（发群/朋友圈）、一句话版。

最短的推荐语就这句：

```
想搞清楚自己该往哪走，别再做测评了——问卷问的是"你觉得自己是什么人"，
你填的时候已经在演了。

这个开源工具换了个入口：读你平时让 AI 帮你干的事。你反复在拆什么、写什么、
查什么，这些骗不了人。本地跑，数据不上传：
https://github.com/duanju9/yishi-skill
```

**发之前先确认对方能不能用**（否则他会失败，然后觉得是你吹牛）：

| 条件 | 说明 |
|---|---|
| AI 能执行本地命令 | Claude Code / Cursor / WorkBuddy / Codex 可以；网页版 ChatGPT、豆包、Kimi 不行，读不到本地文件 |
| Python 3.9+ | Windows 用户常没装，让他的 AI 装一个即可，无需任何第三方包 |
| 有过使用记录 | 全新用户只会得到"样本不足"，这是设计如此 |

## 数据从哪来

自动发现以下位置，缺失就跳过：

| Agent | 路径 |
|---|---|
| WorkBuddy | `~/.workbuddy/projects/*/*.jsonl` |
| Claude Code | `~/.claude/projects/*/*.jsonl` |
| Codex | `~/.codex/sessions/**/*.jsonl` |
| Cursor | `~/.cursor/projects/**/*.jsonl` |
| 记忆文件 | `~/.claude/CLAUDE.md`、`~/.workbuddy/memory/*.md`、`AGENTS.md` |
| ChatGPT 导出 | `--extra conversations.json` |

全程本地读取，脚本内无任何网络调用。默认脱敏（邮箱 / 手机 / 身份证 / 密钥 / URL token / 用户名路径）。

## 模型概要

- **10 维动作倾向**：拆解、建构、表达、探究、决断、协调、秩序、创造、交易、专注。用占比映射而非绝对计数，跨用户可比。
- **适配分**：非对称匹配——低于需求是硬伤全额扣，高于需求是冗余打五五折；再加"强项闲废"惩罚（岗位不看重而你明显强的维度，每条扣 2.5），这是内耗的量化来源。
- **社会距离**：岗位结构性开放度 + 语料里"岗位词 × 人脉词"共现修正。
- **四象限**：适配中位数为纵轴分界、社会距离 60 为横轴分界。
- **扰动层**：只改权重不改骨架。焦虑拉满时社会距离权重也只从 0.45 升到 0.57。

细节见 `references/model.md`，证据判定规则见 `references/evidence-rules.md`。

## 它不能做什么

诚实写在前面，因为这些正是同类工具最爱含糊的地方：

1. **读的是委托行为，不是工作交付**。它知道你让 AI 干了什么，不知道你在公司里做成了什么。能判断兴趣与思考方式，不能判断绩效。
2. **人格倾向 ≠ 胜任力**。拆解欲强不代表能做投研，后者还需要财务基础与承压能力。
3. **社会距离的个人部分是推断**。没提过前辈不等于没有，提过也不等于能内推。
4. **它不是决定者**。报告只回答"合不合手、够不够得着"，不回答"你该选哪个"。
5. **样本少时不可用**。低于 30 条会明确告知"只能当草稿"。

## 目录结构

```
yishi-skill/
├── SKILL.md                    # skill 入口：工作流、规则、故障排查
├── scripts/
│   ├── collect_sessions.py     # 跨 Agent 会话采集（只读、脱敏）
│   ├── score.py                # 10 维画像 + 适配/社会距离 + 四象限
│   └── render.py               # 数据注入模板，产出单文件报告
├── assets/
│   ├── library.json            # 7 岗位需求向量 / 9 人物决策指纹 / 12 书籍索引
│   └── report-template.html    # 报告模板（雷达图 + 散点 + 滑块，离线可用）
├── references/
│   ├── model.md                # 模型原理与调参
│   ├── evidence-rules.md       # 什么算证据、什么必须过滤
│   └── red-lines.md            # 隐私与合规红线
└── README.md
```

## 隐私

你的会话数据永远不会离开你的电脑。三个脚本都没有联网代码，生成的 `corpus.json` / `report-data.json` / 报告 HTML 都含个人数据，`.gitignore` 已排除，请勿提交或上传。

详见 `references/red-lines.md`。

## License

MIT
