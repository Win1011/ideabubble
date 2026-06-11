# 灵感泡泡

这是一个 Codex skill 项目,用于把日常闲聊里冒出来的想法整理成 Obsidian 兼容的 markdown "泡泡",并生成可交互的想法关系图谱。

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
