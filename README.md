# 灵感泡泡

灵感泡泡是一个给 AI 助手使用的个人灵感整理 skill。它把日常聊天里突然冒出来的想法、隐约成形的判断、还没来得及展开的念头,整理成一个个 Obsidian 兼容的 Markdown "泡泡",再通过 `[[双链]]` 把相关想法连接起来,生成一张可以浏览、拖拽和回看的灵感关系图谱。

这个项目的重点不是做一个传统笔记工具,而是让灵感在对话中自然生长:你可以随口聊一个想法,让 AI 助手帮你提炼、命名、查重、补充关联,最后沉淀到本地泡泡库里。时间久了,图谱会逐渐显露出想法之间的重复主题、隐藏线索和新的组合空间。

它适合用来记录产品点子、创作灵感、学习联想、生活观察,也适合把那些"现在还说不清,但好像有点意思"的东西先轻轻收起来。每个泡泡都是普通 `.md` 文件,可以被 Obsidian 打开和继续编辑;生成的 `图谱.html` 不依赖外部服务,离线也能查看。

## 可以给谁用

当前仓库已经按 Codex skill 的结构整理好,可以直接安装到 Codex 使用。它也不依赖 Codex 专有能力:核心内容是 `SKILL.md` 里的工作流说明、泡泡笔记格式和一个本地 Python 图谱生成脚本。因此,Claude、Claude Code 或其他支持自定义指令/技能文件/本地脚本的 AI agent 也可以复用这套方法。

需要注意的是,不同平台的安装方式不一样:Codex 可以直接使用本仓库的 `skill/` 目录;Claude 侧通常需要把 `SKILL.md` 和 `scripts/` 作为自定义 Skill、项目说明或上下文材料导入,并允许它读取泡泡库、运行图谱脚本。

## 本地位置

- 当前项目目录: `/Users/xinyuewang/Documents/灵感泡泡`
- Codex skill 安装目录: `/Users/xinyuewang/.codex/skills/灵感泡泡`
- 图谱输出文件: `图谱.html`

## 目录结构

```text
.
├── README.md
├── 图谱.html
└── skill
    ├── SKILL.md
    └── scripts
        └── build_graph.py
```

## 使用方式

生成图谱:

```bash
python3 skill/scripts/build_graph.py . -o 图谱.html
```

在 Codex 中使用时,skill 的运行说明位于 `skill/SKILL.md`。实际安装到 Codex 后,默认泡泡库位置会按说明使用 `~/灵感泡泡/`。
