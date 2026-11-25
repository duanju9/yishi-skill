# 奕识 · 三维决策系统

> 不问你说自己是谁，只读你实际做过什么。

一个 Claude Code / WorkBuddy / Cursor 通用的 skill：读取你本机已有的 AI 会话与记忆，还原真实行为证据，算出你与 7 条职业路径的**加权适配排序**，并生成一份可以直接打开的可视化报告。

## 它解决什么问题

所有职业测评都在问"你是什么样的人"。但自述会撒谎——尤其是在焦虑、在羡慕别人的时候。

这个工具换了个入口：**你反复让 AI 帮你做什么，比你怎么描述自己更诚实。** 没人会连续三个月委托自己讨厌的事。

## 输出长什么样

跑完会得到一份单文件 HTML（约 50 KB，离线可看），包含：

| 板块 | 内容 |
|---|---|
| 底色轴 | 10 维动作倾向雷达图，证据不足的维度灰显为"未知" |
| 证据 | 增益 / 损耗动作清单，每条带出现次数、占比、脱敏后的原文样本 |
| 双分推演 | 7 个岗位的适配分 × 社会距离，四象限散点图，点开看三情景 |
| 扰动校准 | 拖动焦虑 / 滤镜 / 抗压滑块，看排序怎么变、骨架稳不稳 |
| 历史人物 | 9 位人物的决策节点指纹（约束 / 可选 / 放弃 / 守住 / 代价），附"不能类比之处" |
| 书籍 | 12 本按"回答什么决策问题"索引，分"现在读"与"现在不必读" |
| 边界 | 这份报告不能回答什么 |

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

### 方式一：让 AI 自己装（推荐）

把下面这段直接粘给 Claude Code / WorkBuddy / Cursor：

```
安装并使用奕识决策 skill：
仓库地址 https://github.com/<your-name>/yishi-skill
1. 把仓库克隆到你的 skills 目录（如 ~/.claude/skills/ 或 ~/.workbuddy/skills/）
2. 读取 yishi-skill/SKILL.md，严格按里面的工作流执行
3. 先采集我本机的 AI 会话与记忆，把采集到的数据范围念给我确认
4. 问我心里有没有预设方向，然后建模、生成报告、用文字讲结论
注意：不要跳过采集步骤自己编分数。
```

### 方式二：手动

```bash
git clone https://github.com/<your-name>/yishi-skill.git ~/.workbuddy/skills/yishi-skill
```

然后对它说："用奕识分析我该做什么方向。"

## 手动跑（不装 skill 也能用）

```bash
cd yishi-skill

# 1. 采集（默认最近 180 天，自动脱敏）
python scripts/collect_sessions.py --out corpus.json --since 180

# 2. 建模（--preset 填你心里的预设：research/content/product/consulting/engineering/strategy/founder）
python scripts/score.py --corpus corpus.json --out report-data.json --preset product

# 3. 渲染
python scripts/render.py --data report-data.json --out 我的决策报告.html
```

只依赖 Python 3.9+ 标准库，不需要 pip 安装任何东西。

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
