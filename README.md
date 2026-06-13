# 灵感泡泡

灵感泡泡是一个给 AI 助手使用的个人灵感整理 skill。它把日常聊天里突然冒出来的想法、隐约成形的判断、还没来得及展开的念头,整理成一个个 Obsidian 兼容的 Markdown "泡泡",再通过 `[[双链]]` 把相关想法连接起来,生成一张可以浏览、拖拽和回看的灵感关系图谱。

这个项目的重点不是做一个传统笔记工具,而是让灵感在对话中自然生长:你可以随口聊一个想法,让 AI 助手帮你提炼、命名、查重、补充关联,最后沉淀到本地泡泡库里。时间久了,图谱会逐渐显露出想法之间的重复主题、隐藏线索和新的组合空间。

它适合用来记录产品点子、创作灵感、学习联想、生活观察,也适合把那些"现在还说不清,但好像有点意思"的东西先轻轻收起来。每个泡泡都是普通 `.md` 文件,可以被 Obsidian 打开和继续编辑;生成的 `图谱.html` 不依赖外部服务,离线也能查看。

## 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/Win1011/ideabubble.git
cd ideabubble

# 2. 创建泡泡库(或用 examples/ 先体验)
mkdir -p ~/灵感泡泡
cp examples/*.md ~/灵感泡泡/ 2>/dev/null || true
cp -r examples/示例项目A ~/灵感泡泡/ 2>/dev/null || true

# 3. 生成图谱
python3 skill/scripts/build_graph.py ~/灵感泡泡
open ~/灵感泡泡/图谱.html   # macOS
# xdg-open ~/灵感泡泡/图谱.html   # Linux
```

不需要安装 pip 依赖,只需要 Python 3。

## 安装 Skill

把 `skill/` 目录复制到你使用的 AI 助手的 skills 目录下,文件夹名保持 `灵感泡泡`:

| 平台 | 安装位置 |
|------|----------|
| **Codex** | `~/.codex/skills/灵感泡泡/` |
| **Claude Code** | `~/.claude/skills/灵感泡泡/` |
| **Cursor** | `~/.cursor/skills/灵感泡泡/` 或 `~/.cursor/skills-cursor/灵感泡泡/` |

复制后目录结构应类似:

```text
灵感泡泡/
├── SKILL.md
└── scripts/
    ├── build_graph.py
    ├── manage_project.py
    └── project_server.py
```

安装完成后,对你的 AI 助手说「来聊会儿天」或「帮我记下这个灵感」,它会按 `SKILL.md` 里的流程工作。

### 各平台差异

- **Codex**: 可直接使用内置浏览器打开 `http://localhost:8765/图谱.html`
- **Claude Code / Cursor**: 生成图谱后用系统浏览器打开,或运行 `project_server.py` 后访问本地链接
- 所有平台都需要允许 AI 助手读取 `~/灵感泡泡/` 和运行 `python3` 脚本

## 位置说明

仓库里不会写入任何人的本机路径。每个用户安装后,实际位置由 AI 助手按当前机器环境告知:

- **项目目录**: 当前克隆或解压本仓库的位置
- **Skill 目录**: 上表中的 skills 安装路径
- **泡泡库**: 默认 `~/灵感泡泡/`,可迁移到任意位置
- **图谱文件**: 泡泡库里的 `图谱.html`(由脚本生成,不纳入 git)

迁移泡泡库时,移动整个文件夹即可;之后所有命令都使用新的 `--vault` 路径。

## 目录结构

```text
.
├── LICENSE
├── README.md
├── examples/              # 示例泡泡,可复制到 ~/灵感泡泡/ 体验
│   ├── 跨游戏的情绪存档.md
│   ├── 桌面陪伴.md
│   ├── 最小验证.md
│   └── 示例项目A/
│       └── 侧边助手.md
└── skill/
    ├── SKILL.md           # AI 助手工作流说明
    └── scripts/
        ├── build_graph.py
        ├── manage_project.py
        └── project_server.py
```

`图谱.html` 是生成物,运行脚本后出现在泡泡库里,不在仓库中。

## 使用方式

生成图谱:

```bash
python3 skill/scripts/build_graph.py ~/灵感泡泡
```

用示例数据预览:

```bash
python3 skill/scripts/build_graph.py examples -o /tmp/图谱.html
open /tmp/图谱.html
```

启动可管理项目的图谱服务(支持页面内新建项目、导出):

```bash
python3 skill/scripts/project_server.py --vault ~/灵感泡泡 --port 8765
# 浏览器打开 http://localhost:8765/图谱.html
```

新建/改名项目文件夹:

```bash
python3 skill/scripts/manage_project.py create "项目名" --vault ~/灵感泡泡
python3 skill/scripts/manage_project.py rename "旧项目名" "新项目名" --vault ~/灵感泡泡
```

## 泡泡格式

每个泡泡是一个 `.md` 文件,文件名即标题。frontmatter 示例:

```markdown
---
created: 2026-06-11
created_at: 2026-06-11T22:53:00+08:00
topics: [产品, 游戏]
---

想法本身,一两段话。

原句:
> 用户当时说过的一两句关键原话。

关联:[[另一个泡泡的标题]]、[[再一个]]
```

`created` 用于按天分组,`created_at` 记录精确时间戳。更多格式说明见 `skill/SKILL.md`。

## 项目文件夹

项目是泡泡库下的一层文件夹。例如 `示例项目A/侧边助手.md` 会在图谱里显示为 `示例项目A` 项目下的泡泡。根目录下的 `.md` 是自由泡泡。

图谱生成器会递归扫描项目文件夹,并在页面顶部提供 `全部项目`、`自由泡泡` 和具体项目的筛选。项目文件夹只是收纳视角,不会替代 `[[双链]]`:一个项目里的泡泡仍然可以连接到其他项目或根目录的泡泡。

如果通过 `project_server.py` 打开图谱,页面顶部的项目选择器可以直接筛选项目、新建项目,并通过项目右侧的小铅笔 icon 改名。普通静态打开 `图谱.html` 只能查看,不能创建文件夹或写入导出文件。

`导出/` 是系统生成目录,不会作为项目显示,里面的导出文件也不会被图谱扫描成泡泡。

## 导出和迁移

给 Obsidian 用时,直接把泡泡库文件夹作为 vault 打开即可。每个泡泡本来就是一个普通 `.md` 文件,关联也使用 Obsidian 兼容的 `[[双链]]`。

图谱页面右上角 `更多` 菜单支持:

- `Markdown 索引`: 把所有泡泡汇总成一个 `.md`
- `灵感收成`: 最近新增、热门主题、连接最多泡泡小结
- `JSON 数据`: 适合程序处理
- `CSV 表格`: 适合表格软件筛选整理

通过 `project_server.py` 使用时,导出文件会写入泡泡库下的 `导出/` 文件夹。

## 继续发散

图谱页左下角有「继续聊聊」按钮,随机取一个泡泡并给出 5 条发散话题(产品化、反向质疑、跨领域类比等)。点一下可复制,拿去和 AI 继续聊。

## 许可

[MIT License](LICENSE) — 可自由使用、修改和分发,包括商用。详见下方 License 讨论。

## 隐私说明

- 所有数据存在用户本机,不上传云端
- 不需要 API Key 或账号
- 请勿把个人泡泡库 commit 到公开仓库;本项目的 `.gitignore` 已排除根目录下的 `.md` 文件
