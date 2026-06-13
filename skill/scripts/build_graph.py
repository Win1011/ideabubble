#!/usr/bin/env python3
"""灵感泡泡图谱生成器。

扫描泡泡库里的 .md 文件(文件名即标题,frontmatter 带 created/topics,
正文里的 [[双链]] 是关联),生成一个自包含的交互式 HTML 图谱:
- 图谱视图:力导向布局,可拖拽/缩放,Obsidian 风格
- 时间线视图:按日期分列,跨天关联画弧线
不依赖任何外部库或 CDN,离线可用。

用法: python3 build_graph.py [泡泡库目录] [-o 输出.html]
默认库目录 ~/灵感泡泡,默认输出 <库>/图谱.html
"""

import argparse
import datetime
import html
import json
import re
import sys
from pathlib import Path

LINK_RE = re.compile(r"\[\[([^\]\|#]+)(?:[#|][^\]]*)?\]\]")
RESERVED_DIRS = {"skill", "scripts", "node_modules", "__pycache__", "导出"}


def parse_frontmatter(text):
    meta = {}
    body = text
    if text.startswith("---"):
        parts = text.split("\n---", 2)
        if len(parts) >= 2:
            fm = parts[0].lstrip("-\n")
            body = parts[1].lstrip("-").lstrip("\n") if len(parts) == 2 else (
                parts[1].lstrip("-").lstrip("\n")
            )
            # 重新可靠切分:第一行是 ---,找下一个单独成行的 ---
            lines = text.splitlines()
            end = None
            for i, line in enumerate(lines[1:], start=1):
                if line.strip() == "---":
                    end = i
                    break
            if end is not None:
                fm = "\n".join(lines[1:end])
                body = "\n".join(lines[end + 1:]).lstrip("\n")
            for line in fm.splitlines():
                if ":" not in line:
                    continue
                key, _, val = line.partition(":")
                meta[key.strip()] = val.strip()
    return meta, body


def parse_topics(raw):
    if not raw:
        return []
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return [t.strip().strip("'\"") for t in raw.split(",") if t.strip().strip("'\"")]


def parse_date(raw, fallback_path):
    if raw:
        m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
        if m:
            try:
                return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass
    ts = fallback_path.stat().st_mtime
    return datetime.date.fromtimestamp(ts)


def body_to_html(body):
    """极简 markdown 渲染:段落、引用、加粗、双链。"""
    text = html.escape(body)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)

    def link_repl(m):
        target = m.group(1).strip()
        return '<a class="wl" data-id="%s">%s</a>' % (html.escape(target, quote=True), html.escape(target))

    text = re.sub(r"\[\[([^\]\|#]+)(?:[#|][^\]]*)?\]\]", link_repl, text)
    blocks = []
    for p in [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]:
        normal = []
        quote = []

        def flush_normal():
            if normal:
                blocks.append("<p>%s</p>" % "<br>".join(normal))
                normal.clear()

        def flush_quote():
            if quote:
                blocks.append("<blockquote>%s</blockquote>" % "<br>".join(quote))
                quote.clear()

        for line in p.splitlines():
            stripped = line.strip()
            if stripped.startswith("&gt;"):
                flush_normal()
                quote.append(stripped[4:].strip())
            else:
                flush_quote()
                normal.append(line)
        flush_normal()
        flush_quote()
    return "".join(blocks)


def make_suggestions(title, topics, links):
    """生成五条相关但不同方向的继续聊话题。"""
    topic_hint = "、".join(topics[:2]) if topics else "这个想法"
    linked_hint = links[0] if links else "另一个旧泡泡"
    return [
        f"如果把「{title}」做成一个最小产品,第一屏应该让用户看到什么?",
        f"反过来想:「{title}」最可能不成立、最容易变无聊的地方在哪里?",
        f"围绕「{topic_hint}」换一个完全不同领域,「{title}」会变成什么?",
        f"从用户情绪看,「{title}」解决的是焦虑、好奇、陪伴、成就感里的哪一种?",
        f"沿着「{linked_hint}」继续发散,它和「{title}」能组合出一个什么新方向?",
    ][:5]


def should_skip_path(vault, path):
    rel = path.relative_to(vault)
    if any(part.startswith(".") for part in rel.parts):
        return True
    if rel.parts and rel.parts[0] in RESERVED_DIRS:
        return True
    if path.name.startswith("_") or path.name.lower() in {"readme.md", "skill.md"}:
        return True
    if path.stem == "图谱":
        return True
    return False


def should_skip_project_dir(path):
    if path.name.startswith("."):
        return True
    return path.name in RESERVED_DIRS


def collect(vault):
    nodes = {}
    order = []
    for path in sorted(vault.rglob("*.md")):
        if should_skip_path(vault, path):
            continue
        rel = path.relative_to(vault)
        project = "" if rel.parent == Path(".") else rel.parent.as_posix()
        title = path.stem
        text = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        if not (meta.get("created") or meta.get("created_at") or meta.get("topics")):
            continue
        created_at = meta.get("created_at") or ""
        date = parse_date(created_at or meta.get("created"), path)
        topics = parse_topics(meta.get("topics"))
        links = [t.strip() for t in LINK_RE.findall(body) if t.strip() and t.strip() != title]
        nodes[title] = {
            "id": title,
            "date": date.isoformat(),
            "created_at": created_at,
            "modified": path.stat().st_mtime,
            "path": rel.as_posix(),
            "project": project,
            "topics": topics,
            "body": body,
            "html": body_to_html(body),
            "links": links,
            "suggestions": make_suggestions(title, topics, links),
            "ghost": False,
        }
        order.append(title)

    # 未解析的链接 → 幽灵泡泡
    for title in list(order):
        for target in nodes[title]["links"]:
            if target not in nodes:
                nodes[target] = {
                    "id": target, "date": None, "created_at": None, "topics": [],
                    "modified": None,
                    "path": None,
                    "project": None,
                    "body": "还没展开的想法——下次聊聊它?",
                    "html": "<p class='ghost-hint'>还没展开的想法——下次聊聊它?</p>",
                    "links": [],
                    "suggestions": make_suggestions(target, [], []),
                    "ghost": True,
                }
                order.append(target)

    index = {t: i for i, t in enumerate(order)}
    edge_set = set()
    for title in order:
        for target in nodes[title]["links"]:
            a, b = index[title], index[target]
            edge_set.add((min(a, b), max(a, b)))

    topic_order = []
    for t in order:
        for tp in nodes[t]["topics"]:
            if tp not in topic_order:
                topic_order.append(tp)
    project_order = []
    for t in order:
        project = nodes[t].get("project")
        if project and project not in project_order:
            project_order.append(project)
    for path in sorted(p for p in vault.iterdir() if p.is_dir()):
        if should_skip_project_dir(path):
            continue
        project = path.name
        if project not in project_order:
            project_order.append(project)

    return {
        "nodes": [nodes[t] for t in order],
        "edges": sorted(edge_set),
        "topics": topic_order,
        "projects": project_order,
        "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def write_graph(vault, out):
    data = collect(vault)
    html_text = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    out.write_text(html_text, encoding="utf-8")
    return data


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>灵感泡泡</title>
<style>
:root {
  --bg: #fbfbfa;
  --ink: #1f1f1f;
  --muted: #7b7b78;
  --soft: #f1f1ef;
  --line: rgba(31,31,31,.10);
  --panel: rgba(255,255,255,.92);
  --panel-strong: #ffffff;
  --accent: #111111;
  --accent-soft: rgba(31,31,31,.08);
  --shadow: 0 22px 70px rgba(15, 15, 15, .10);
  --shadow-soft: 0 8px 28px rgba(15, 15, 15, .07);
}
* { box-sizing: border-box; margin: 0; }
body {
  background: var(--bg);
  color: var(--ink);
  font: 14px/1.6 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
  overflow: hidden;
}
body::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(31,31,31,.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(31,31,31,.025) 1px, transparent 1px);
  background-size: 28px 28px;
  mask-image: linear-gradient(to bottom, rgba(0,0,0,.55), transparent 76%);
}
header {
  position: fixed;
  top: 14px;
  left: 16px;
  right: 16px;
  z-index: 10;
  min-height: 60px;
  display: grid;
  grid-template-columns: minmax(176px, auto) minmax(220px, 1fr) auto;
  align-items: center;
  gap: 14px;
  padding: 10px 10px 10px 14px;
  background: rgba(255,255,255,.88);
  backdrop-filter: blur(18px) saturate(1.1);
  border: 1px solid rgba(31,31,31,.08);
  border-bottom-color: var(--line);
  border-radius: 12px;
  box-shadow: var(--shadow-soft);
}
.brand { display: flex; align-items: center; gap: 10px; min-width: 0; }
.mark {
  position: relative;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: #fff;
  border: 1px solid rgba(31,31,31,.13);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.9);
}
.mark::before,
.mark::after {
  content: "";
  position: absolute;
  border-radius: 999px;
}
.mark::before {
  width: 18px;
  height: 18px;
  left: 8px;
  top: 8px;
  background: #111;
}
.mark::after {
  width: 12px;
  height: 12px;
  right: 7px;
  bottom: 7px;
  background: #fff;
  border: 2px solid #111;
}
header h1 { font-size: 15px; line-height: 1.1; font-weight: 720; letter-spacing: 0; }
#stats { color: var(--muted); font-size: 12px; white-space: nowrap; }
.tools { display: flex; justify-content: center; align-items: center; gap: 8px; min-width: 0; }
.actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; min-width: 0; }
.search-wrap {
  position: relative;
  width: min(420px, 100%);
}
.search-wrap .ico-search {
  position: absolute;
  left: 13px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--muted);
  pointer-events: none;
}
.ico-search::before {
  content: "";
  position: absolute;
  width: 8px;
  height: 8px;
  left: 1px;
  top: 1px;
  border: 1.7px solid currentColor;
  border-radius: 50%;
}
.ico-search::after {
  content: "";
  position: absolute;
  width: 6px;
  height: 1.7px;
  left: 8px;
  top: 10px;
  background: currentColor;
  transform: rotate(45deg);
  transform-origin: left center;
}
.search {
  width: 100%;
  height: 38px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
  color: var(--ink);
  padding: 0 15px 0 35px;
  outline: none;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.72);
}
.search::placeholder { color: rgba(119,116,107,.76); }
.search:focus { border-color: rgba(31,31,31,.34); box-shadow: 0 0 0 4px var(--accent-soft); }
.project-picker { position: relative; min-width: 148px; }
.project-filter {
  height: 38px;
  width: 100%;
  min-width: 148px;
  max-width: 220px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
  color: var(--ink);
  padding: 0 30px 0 12px;
  outline: none;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.72);
  cursor: pointer;
  text-align: left;
  position: relative;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.project-filter::after {
  content: "";
  position: absolute;
  right: 12px;
  top: 50%;
  width: 7px;
  height: 7px;
  border-right: 1.5px solid currentColor;
  border-bottom: 1.5px solid currentColor;
  transform: translateY(-65%) rotate(45deg);
  opacity: .65;
}
.project-filter:focus { border-color: rgba(31,31,31,.34); box-shadow: 0 0 0 4px var(--accent-soft); }
.project-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 24;
  width: 280px;
  max-height: min(520px, calc(100vh - 110px));
  overflow: auto;
  padding: 8px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: rgba(255,255,255,.98);
  color: var(--ink);
  box-shadow: var(--shadow-soft);
  backdrop-filter: blur(18px);
}
.project-menu[hidden] { display: none; }
.project-menu-section { display: grid; gap: 4px; padding-bottom: 7px; }
.project-menu-section + .project-menu-section { border-top: 1px solid var(--line); padding-top: 8px; }
.project-option-row { display: grid; grid-template-columns: minmax(0, 1fr) 28px; gap: 4px; align-items: center; }
.project-option,
.project-icon {
  height: 32px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--ink);
  cursor: pointer;
}
.project-option {
  text-align: left;
  padding: 0 9px;
  font: inherit;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.project-option:hover,
.project-icon:hover { background: var(--soft); }
.project-option.on { background: var(--ink); color: #fff; }
.project-icon {
  position: relative;
  color: var(--muted);
}
.project-icon::before {
  content: "";
  position: absolute;
  left: 8px;
  top: 15px;
  width: 12px;
  height: 3px;
  border-radius: 2px;
  background: currentColor;
  transform: rotate(-38deg);
  transform-origin: center;
}
.project-icon::after {
  content: "";
  position: absolute;
  left: 17px;
  top: 10px;
  width: 4px;
  height: 4px;
  border-radius: 1px;
  background: currentColor;
  transform: rotate(-38deg);
}
.project-inline-form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 6px;
  padding: 5px 0 6px;
}
.project-inline-form[hidden] { display: none; }
.project-inline-form input {
  min-width: 0;
  height: 32px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
  color: var(--ink);
  padding: 0 9px;
  outline: none;
}
.project-inline-form button,
.project-create button {
  height: 32px;
  border: 0;
  border-radius: 8px;
  background: var(--ink);
  color: #fff;
  cursor: pointer;
  padding: 0 10px;
}
.project-create { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px; }
.project-create label,
.project-menu-status {
  grid-column: 1 / -1;
  color: var(--muted);
  font-size: 11px;
}
.project-create input {
  min-width: 0;
  height: 32px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
  color: var(--ink);
  padding: 0 9px;
  outline: none;
}
.project-menu-status.error { color: #9f1d1d; }
.tabs {
  display: inline-flex;
  gap: 3px;
  padding: 3px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--soft);
}
.tabs button {
  height: 32px;
  min-width: 62px;
  background: transparent;
  border: 0;
  color: var(--muted);
  padding: 0 13px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
}
.tabs button.on { color: #fff; background: var(--ink); box-shadow: 0 8px 18px rgba(31,31,31,.13); }
.ico {
  position: relative;
  width: 14px;
  height: 14px;
  display: inline-block;
  flex: 0 0 auto;
}
.ico-graph::before,
.ico-graph::after {
  content: "";
  position: absolute;
  border-radius: 999px;
  background: currentColor;
}
.ico-graph::before { width: 6px; height: 6px; left: 1px; top: 2px; box-shadow: 7px 5px 0 currentColor; }
.ico-graph::after { width: 9px; height: 1.5px; left: 4px; top: 7px; transform: rotate(35deg); opacity: .65; }
.ico-time::before {
  content: "";
  position: absolute;
  inset: 1px;
  border: 1.8px solid currentColor;
  border-radius: 999px;
}
.ico-time::after {
  content: "";
  position: absolute;
  left: 7px;
  top: 4px;
  width: 1.6px;
  height: 5px;
  background: currentColor;
  box-shadow: 3px 4px 0 -1px currentColor;
}
.ico-more::before {
  content: "";
  position: absolute;
  left: 1px;
  top: 6px;
  width: 3px;
  height: 3px;
  border-radius: 999px;
  background: currentColor;
  box-shadow: 5px 0 0 currentColor, 10px 0 0 currentColor;
}
.export { position: relative; }
.export-toggle {
  height: 38px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
  color: var(--ink);
  padding: 0 14px;
  cursor: pointer;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.72);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  white-space: nowrap;
}
.export-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 220px;
  display: none;
  padding: 7px;
  background: rgba(255,255,255,.98);
  border: 1px solid rgba(31,31,31,.09);
  border-bottom-color: var(--line);
  border-radius: 12px;
  box-shadow: var(--shadow-soft);
  backdrop-filter: blur(18px);
}
.export.open .export-menu { display: block; }
.export-menu button {
  width: 100%;
  display: block;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--ink);
  text-align: left;
  padding: 9px 10px;
  cursor: pointer;
  font: inherit;
}
.export-menu button:hover { background: var(--soft); }
.export-menu small { display: block; color: var(--muted); font-size: 11px; line-height: 1.35; margin-top: 1px; }
.export-status {
  min-height: 18px;
  padding: 4px 10px 2px;
  color: var(--muted);
  font-size: 11px;
  word-break: break-all;
}
.export-status a { color: var(--ink); text-decoration: none; border-bottom: 1px solid rgba(31,31,31,.25); }
.project-modal {
  position: fixed;
  inset: 0;
  z-index: 30;
  display: flex;
  justify-content: flex-end;
  align-items: stretch;
  padding: 10px;
  background: rgba(31,31,31,.12);
  backdrop-filter: blur(5px);
}
.project-modal[hidden] { display: none; }
.project-card {
  width: min(390px, calc(100vw - 20px));
  height: 100%;
  padding: 0;
  background: rgba(255,255,255,.98);
  border: 1px solid rgba(31,31,31,.10);
  border-radius: 12px;
  box-shadow: var(--shadow);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.project-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 18px 15px;
  border-bottom: 1px solid var(--line);
  background: #fff;
}
.project-card h2 { font-size: 17px; line-height: 1.2; }
.project-card p {
  margin-top: 4px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.45;
}
.project-card .close {
  position: static;
  width: 30px;
  height: 30px;
  flex: 0 0 auto;
}
.project-sheet-body {
  display: grid;
  gap: 12px;
  padding: 14px;
  overflow: auto;
}
.project-form {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
  padding: 13px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fff;
}
.project-form.rename { grid-template-columns: 1fr; }
.project-form label {
  grid-column: 1 / -1;
  color: var(--ink);
  font-size: 13px;
  font-weight: 650;
}
.project-form small {
  grid-column: 1 / -1;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.45;
  margin-top: -5px;
}
.project-form input,
.project-form select {
  height: 38px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
  color: var(--ink);
  padding: 0 11px;
  outline: none;
}
.project-form button {
  height: 36px;
  min-width: 72px;
  border: 0;
  border-radius: 8px;
  background: var(--ink);
  color: #fff;
  cursor: pointer;
  padding: 0 13px;
}
.project-form button:disabled { opacity: .45; cursor: not-allowed; }
.project-status {
  min-height: 20px;
  padding: 0 4px;
  color: var(--muted);
  font-size: 12px;
}
.project-status.error { color: #9f1d1d; }
#view-graph, #view-timeline { position: fixed; inset: 0; padding-top: 86px; }
#cv { width: 100%; height: 100%; display: block; cursor: grab; }
#view-timeline { overflow: auto; }
#view-timeline svg { display: block; }
.legend {
  position: fixed;
  left: 18px;
  bottom: 18px;
  z-index: 10;
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  max-width: min(680px, calc(100vw - 36px));
  font-size: 12px;
  color: var(--muted);
}
.legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 28px;
  padding: 4px 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: rgba(255,255,255,.88);
  backdrop-filter: blur(12px);
  box-shadow: 0 7px 18px rgba(15,15,15,.04);
}
.legend i { width: 8px; height: 8px; border-radius: 50%; display: inline-block; box-shadow: 0 0 0 3px rgba(31,31,31,.05); }
#panel {
  position: fixed;
  top: 88px;
  right: 16px;
  bottom: 16px;
  width: 370px;
  max-width: calc(100vw - 32px);
  z-index: 11;
  background: var(--panel);
  border: 1px solid rgba(31,31,31,.09);
  border-bottom-color: var(--line);
  border-radius: 14px;
  box-shadow: var(--shadow);
  backdrop-filter: blur(24px) saturate(1.15);
  padding: 22px;
  overflow-y: auto;
  transform: translateX(calc(100% + 26px));
  transition: transform .26s cubic-bezier(.2,.8,.2,1);
}
#panel.open { transform: none; }
#panel .close {
  position: absolute;
  top: 14px;
  right: 14px;
  width: 32px;
  height: 32px;
  background: var(--soft);
  border: 0;
  border-radius: 50%;
  color: var(--muted);
  font-size: 18px;
  cursor: pointer;
}
#panel h2 { font-size: 22px; line-height: 1.2; margin-bottom: 8px; padding-right: 36px; letter-spacing: 0; }
#panel .meta { color: var(--muted); font-size: 12px; margin-bottom: 18px; display: flex; flex-wrap: wrap; gap: 7px; align-items: center; }
#panel .chip { border: 1px solid var(--line); border-radius: 6px; padding: 2px 8px; font-size: 11px; background: var(--soft); }
#panel .body p { margin-bottom: 12px; color: #333129; }
#panel .body blockquote {
  margin: 10px 0 14px;
  padding: 10px 12px;
  border-left: 3px solid rgba(31,31,31,.32);
  background: rgba(31,31,31,.04);
  color: #3d3b35;
  border-radius: 0 8px 8px 0;
}
#panel .links { margin-top: 18px; border-top: 1px solid var(--line); padding-top: 14px; }
#panel .links h3 { font-size: 12px; color: var(--muted); font-weight: 650; margin-bottom: 8px; }
#panel .links div { margin: 6px 0; }
.ideas { margin-top: 18px; border-top: 1px solid var(--line); padding-top: 14px; }
.ideas h3 { font-size: 12px; color: var(--muted); font-weight: 650; margin-bottom: 8px; }
.home-ideas {
  position: fixed;
  left: 16px;
  bottom: 16px;
  z-index: 8;
  width: min(430px, calc(100vw - 32px));
  padding: 16px;
  background: rgba(255,255,255,.90);
  border: 1px solid rgba(31,31,31,.09);
  border-bottom-color: var(--line);
  border-radius: 14px;
  box-shadow: var(--shadow-soft);
  backdrop-filter: blur(22px) saturate(1.1);
}
.home-ideas:not(.open) { display: none; }
.idea-launcher {
  position: fixed;
  left: 16px;
  bottom: 16px;
  z-index: 8;
  height: 44px;
  min-width: 122px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 14px;
  border: 1px solid rgba(31,31,31,.10);
  border-radius: 999px;
  background: rgba(255,255,255,.92);
  color: var(--ink);
  box-shadow: var(--shadow-soft);
  backdrop-filter: blur(20px) saturate(1.1);
  font: inherit;
  font-weight: 650;
  cursor: pointer;
}
.idea-launcher:hover { background: #fff; }
.bulb-icon {
  position: relative;
  width: 17px;
  height: 20px;
  flex: 0 0 auto;
}
.bulb-icon::before {
  content: "";
  position: absolute;
  left: 3px;
  top: 1px;
  width: 11px;
  height: 12px;
  border: 2px solid currentColor;
  border-bottom: 0;
  border-radius: 999px 999px 7px 7px;
}
.bulb-icon::after {
  content: "";
  position: absolute;
  left: 5px;
  bottom: 1px;
  width: 7px;
  height: 5px;
  border-top: 2px solid currentColor;
  border-bottom: 2px solid currentColor;
  border-radius: 2px;
}
.home-ideas-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 10px;
}
.home-ideas-title { min-width: 0; }
.home-ideas h2 {
  font-size: 13px;
  line-height: 1.3;
  letter-spacing: 0;
  margin-bottom: 2px;
}
.home-ideas .source {
  color: var(--muted);
  font-size: 11px;
  line-height: 1.35;
}
.cycle-ideas {
  flex: 0 0 auto;
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--soft);
  color: var(--ink);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.cycle-ideas:hover { background: #fff; }
.close-ideas {
  flex: 0 0 auto;
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 50%;
  background: var(--soft);
  color: var(--muted);
  font-size: 17px;
  line-height: 1;
  cursor: pointer;
}
.close-ideas:hover { background: #fff; color: var(--ink); }
.idea-list { display: grid; gap: 8px; }
.idea-btn {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fff;
  color: var(--ink);
  padding: 10px 11px;
  text-align: left;
  font: inherit;
  line-height: 1.45;
  cursor: pointer;
}
.idea-btn:hover { background: var(--soft); }
.home-ideas .idea-list { gap: 7px; }
.home-ideas .idea-btn {
  min-height: 38px;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 12px;
}
.copy-tip {
  margin-top: 8px;
  color: var(--muted);
  font-size: 11px;
  min-height: 16px;
}
.copy-toast {
  position: fixed;
  left: 50%;
  bottom: 26px;
  z-index: 30;
  transform: translate(-50%, 16px);
  opacity: 0;
  pointer-events: none;
  padding: 9px 13px;
  border: 1px solid rgba(31,31,31,.13);
  border-radius: 999px;
  background: rgba(31,31,31,.92);
  color: #fff;
  font-size: 13px;
  box-shadow: 0 12px 30px rgba(31,31,31,.2);
  transition: opacity .18s ease, transform .18s ease;
}
.copy-toast.show {
  opacity: 1;
  transform: translate(-50%, 0);
}
a.wl { color: var(--accent); cursor: pointer; text-decoration: none; border-bottom: 1px solid rgba(31,31,31,.24); }
.ghost-hint { color: var(--muted); font-style: italic; }
#empty {
  position: fixed;
  inset: 0;
  z-index: 2;
  display: grid;
  place-items: center;
  padding: 120px 22px 60px;
  color: var(--muted);
  pointer-events: none;
}
.empty-card {
  width: min(560px, 100%);
  padding: 36px;
  text-align: left;
  background: rgba(255,255,255,.92);
  border: 1px solid rgba(31,31,31,.08);
  border-bottom-color: var(--line);
  border-radius: 14px;
  box-shadow: var(--shadow);
  backdrop-filter: blur(22px);
}
.empty-icon {
  position: relative;
  width: 54px;
  height: 38px;
  margin-bottom: 18px;
}
.empty-icon::before,
.empty-icon::after {
  content: "";
  position: absolute;
  border-radius: 999px;
}
.empty-icon::before {
  width: 34px;
  height: 34px;
  left: 0;
  top: 2px;
  background: #111;
}
.empty-icon::after {
  width: 22px;
  height: 22px;
  right: 0;
  top: 0;
  background: #fff;
  border: 2px solid #111;
}
.empty-kicker { color: var(--muted); font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; margin-bottom: 10px; }
.empty-card h2 { color: var(--ink); font-size: clamp(28px, 6vw, 48px); line-height: 1.05; letter-spacing: 0; margin-bottom: 14px; }
.empty-card p { max-width: 42ch; }
@media (max-width: 760px) {
  header {
    grid-template-columns: 1fr auto;
    align-items: center;
    gap: 10px;
    border-radius: 16px;
  }
  .brand { grid-column: 1; grid-row: 1; }
  .tools { grid-column: 1 / -1; grid-row: 2; justify-content: stretch; }
  .actions { display: contents; }
  .actions .export { grid-column: 2; grid-row: 1; justify-self: end; }
  .actions .tabs { grid-column: 1 / -1; grid-row: 3; }
  .search-wrap { width: 100%; }
  .search { width: 100%; }
  .project-picker { width: 100%; }
  .project-filter { max-width: none; }
  .project-menu {
    left: 0;
    right: 0;
    width: auto;
    max-height: min(54vh, 420px);
  }
  .export-toggle { width: 82px; height: 34px; }
  .tabs { justify-content: stretch; }
  .tabs button { flex: 1; }
  #view-graph, #view-timeline { padding-top: 154px; }
  #panel { top: auto; left: 10px; right: 10px; bottom: 10px; width: auto; max-height: 72vh; transform: translateY(calc(100% + 26px)); }
  #panel.open { transform: none; }
  .home-ideas {
    left: 10px;
    right: 10px;
    bottom: 10px;
    width: auto;
    max-height: 42vh;
    overflow-y: auto;
  }
  .idea-launcher {
    left: 10px;
    bottom: 10px;
  }
  .legend { display: none; }
}
</style>
</head>
<body>
<header>
  <div class="brand">
    <div class="mark" aria-hidden="true"></div>
    <div>
      <h1>灵感泡泡</h1>
      <span id="stats"></span>
    </div>
  </div>
  <div class="tools">
    <div class="search-wrap">
      <span class="ico ico-search" aria-hidden="true"></span>
      <input class="search" id="search" type="search" placeholder="搜索泡泡、主题或正文">
    </div>
    <div class="project-picker" id="project-picker">
      <button class="project-filter" id="project-filter-button" type="button" aria-haspopup="true" aria-expanded="false">全部项目</button>
      <div class="project-menu" id="project-menu" hidden>
        <div class="project-menu-section" id="project-options"></div>
        <form class="project-create project-menu-section" id="project-create-form">
          <label for="project-create-name">新建项目</label>
          <input id="project-create-name" name="name" autocomplete="off" placeholder="项目名">
          <button type="submit">新建</button>
        </form>
        <div class="project-menu-status" id="project-status" role="status" aria-live="polite"></div>
      </div>
    </div>
  </div>
  <div class="actions">
    <div class="tabs">
      <button id="tab-graph" class="on"><span class="ico ico-graph"></span>图谱</button>
      <button id="tab-timeline"><span class="ico ico-time"></span>时间线</button>
    </div>
    <div class="export" id="export">
      <button class="export-toggle" id="export-toggle" type="button" aria-haspopup="true" aria-expanded="false"><span class="ico ico-more"></span>更多</button>
      <div class="export-menu" id="export-menu">
        <button type="button" data-export="markdown">Markdown 索引<small>适合 Obsidian、Notion、文档软件</small></button>
        <button type="button" data-export="harvest">灵感收成<small>最近新增、热门主题、组合发散</small></button>
        <button type="button" data-export="json">JSON 数据<small>适合程序、自动化、二次分析</small></button>
        <button type="button" data-export="csv">CSV 表格<small>适合 Numbers、Excel、Sheets</small></button>
        <div class="export-status" id="export-status" role="status" aria-live="polite"></div>
      </div>
    </div>
  </div>
</header>
<div id="view-graph"><canvas id="cv"></canvas></div>
<div id="view-timeline" hidden></div>
<div class="legend" id="legend"></div>
<div class="copy-toast" id="copy-toast" role="status" aria-live="polite"></div>
<button class="idea-launcher" id="idea-launcher" type="button" aria-controls="home-ideas">
  <span class="bulb-icon" aria-hidden="true"></span>
  继续聊聊
</button>
<section class="home-ideas" id="home-ideas" aria-label="继续聊聊">
  <div class="home-ideas-head">
    <div class="home-ideas-title">
      <h2>继续聊聊</h2>
      <div class="source" id="home-ideas-source"></div>
    </div>
    <button class="cycle-ideas" id="cycle-ideas" type="button">换一组</button>
    <button class="close-ideas" id="close-ideas" type="button" aria-label="收起继续聊聊">×</button>
  </div>
  <div class="idea-list" id="home-ideas-list"></div>
  <div class="copy-tip">点一下复制话题,拿去继续聊。</div>
</section>
<aside id="panel">
  <button class="close" id="panel-close">×</button>
  <h2 id="p-title"></h2>
  <div class="meta" id="p-meta"></div>
  <div class="body" id="p-body"></div>
  <div class="ideas" id="p-ideas"></div>
  <div class="links" id="p-links"></div>
</aside>
<script>
const DATA = __DATA__;
const PALETTE = ['#111111','#343434','#565656','#737373','#8c8c8c','#a3a3a3','#242424','#666666','#4a4a4a','#7f7f7f'];
const topicColor = {};
DATA.topics.forEach((t,i)=>topicColor[t]=PALETTE[i%PALETTE.length]);
const GHOST = '#b8b8b8', PLAIN = '#666666';

const N = DATA.nodes, E = DATA.edges;
const deg = N.map(()=>0);
E.forEach(([a,b])=>{deg[a]++;deg[b]++;});
N.forEach((n,i)=>{
  n.idx=i; n.degree=deg[i];
  n.r = n.ghost ? 4.5 : 7 + 3*Math.sqrt(deg[i]);
  n.color = n.ghost ? GHOST : (n.topics.length ? topicColor[n.topics[0]] : PLAIN);
});
const byId = {}; N.forEach(n=>byId[n.id]=n);
const days = [...new Set(N.filter(n=>n.date).map(n=>n.date))].sort();
document.getElementById('stats').textContent =
  N.filter(n=>!n.ghost).length + ' 个泡泡 · ' + (DATA.projects || []).length + ' 个项目 · ' + E.length + ' 条关联 · 跨 ' + days.length + ' 天';

const projectPicker = document.getElementById('project-picker');
const projectFilterButton = document.getElementById('project-filter-button');
const projectMenu = document.getElementById('project-menu');
const projectOptions = document.getElementById('project-options');
const projectStatus = document.getElementById('project-status');
let activeProject = '';
function setProjectStatus(message, isError=false){
  projectStatus.textContent = message;
  projectStatus.classList.toggle('error', isError);
}
async function postProjectApi(path, payload){
  const res = await fetch(path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  });
  let data = {};
  try { data = await res.json(); } catch (_) {}
  if (!res.ok || data.ok === false) throw new Error(data.error || '项目操作失败');
  return data;
}
function projectNameFor(value){
  if (!value) return '全部项目';
  if (value === '__free__') return '自由泡泡';
  return value;
}
function closeProjectMenu(){
  projectMenu.hidden = true;
  projectFilterButton.setAttribute('aria-expanded', 'false');
  setProjectStatus('');
}
function openProjectMenu(){
  renderProjectOptions();
  projectMenu.hidden = false;
  projectFilterButton.setAttribute('aria-expanded', 'true');
}
function applyProject(value){
  activeProject = value;
  projectFilterButton.textContent = projectNameFor(value);
  if (selected && !matchesProject(selected)) {
    panel.classList.remove('open');
    selected = null;
  }
  closeProjectMenu();
  draw();
  if (!document.getElementById('view-timeline').hidden) buildTimeline(true);
}
function renderProjectOptions(renameFor=''){
  const rows = [
    {value: '', label: '全部项目', editable: false},
    {value: '__free__', label: '自由泡泡', editable: false},
    ...(DATA.projects || []).map(project=>({value: project, label: project, editable: true}))
  ];
  projectOptions.innerHTML = rows.map(row=>{
    const on = row.value === activeProject ? ' on' : '';
    const edit = row.editable ? '<button class="project-icon" type="button" data-rename="'+escAttr(row.value)+'" aria-label="改名 '+escAttr(row.label)+'"></button>' : '<span></span>';
    const form = row.editable ? '<form class="project-inline-form" data-rename-form="'+escAttr(row.value)+'" '+(renameFor===row.value?'':'hidden')+'><input name="new_name" autocomplete="off" value="'+escAttr(row.value)+'"><button type="submit">改名</button></form>' : '';
    return '<div><div class="project-option-row"><button class="project-option'+on+'" type="button" data-project="'+escAttr(row.value)+'">'+escHtml(row.label)+'</button>'+edit+'</div>'+form+'</div>';
  }).join('');
}
projectFilterButton.addEventListener('click', e => {
  e.stopPropagation();
  projectMenu.hidden ? openProjectMenu() : closeProjectMenu();
});
document.addEventListener('click', e => {
  if (!projectPicker.contains(e.target)) closeProjectMenu();
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && !projectMenu.hidden) closeProjectMenu();
});
projectOptions.addEventListener('click', e => {
  const rename = e.target.closest('[data-rename]');
  if (rename) {
    e.stopPropagation();
    renderProjectOptions(rename.dataset.rename);
    const input = projectOptions.querySelector('[data-rename-form="'+CSS.escape(rename.dataset.rename)+'"] input');
    if (input) { input.focus(); input.select(); }
    return;
  }
  const option = e.target.closest('[data-project]');
  if (option) applyProject(option.dataset.project || '');
});
projectOptions.addEventListener('submit', async e => {
  const form = e.target.closest('[data-rename-form]');
  if (!form) return;
  e.preventDefault();
  const oldName = form.dataset.renameForm;
  const newName = form.elements.new_name.value.trim();
  if (!newName) { setProjectStatus('先输入新项目名。', true); return; }
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  setProjectStatus('正在改名项目...');
  try {
    await postProjectApi('/api/projects/rename', {old_name: oldName, new_name: newName});
    setProjectStatus('已改名项目,正在刷新图谱。');
    window.location.reload();
  } catch (err) {
    setProjectStatus(err.message || '项目操作失败。', true);
    button.disabled = false;
  }
});
document.getElementById('project-create-form').addEventListener('submit', async e => {
  e.preventDefault();
  const button = e.currentTarget.querySelector('button[type="submit"]');
  const name = document.getElementById('project-create-name').value.trim();
  if (!name) { setProjectStatus('先输入项目名。', true); return; }
  setProjectStatus('正在新建项目...');
  button.disabled = true;
  try {
    await postProjectApi('/api/projects', {name});
    setProjectStatus('已新建项目,正在刷新图谱。');
    window.location.reload();
  } catch (err) {
    setProjectStatus(err.message || '项目操作失败。确认当前页面是项目服务打开的,不是普通静态服务。', true);
    button.disabled = false;
  }
});
renderProjectOptions();

// 图例
const lg = document.getElementById('legend');
lg.innerHTML = DATA.topics.map(t=>'<span><i style="background:'+topicColor[t]+'"></i>'+t+'</span>').join('')
  + (N.some(n=>n.ghost) ? '<span><i style="background:'+GHOST+'"></i>幽灵泡泡(还没展开)</span>' : '');

if (!N.length) {
  document.body.insertAdjacentHTML('beforeend','<div id="empty"><div class="empty-card"><div class="empty-icon" aria-hidden="true"></div><div class="empty-kicker">Idea map</div><h2>还没有泡泡。</h2><p>下次聊天里冒出一个念头时,我会把它整理成 Markdown 泡泡,再把关联慢慢织到这张图里。</p></div></div>');
}

const search = document.getElementById('search');
let query = '';
search.addEventListener('input', () => {
  query = search.value.trim().toLowerCase();
  draw();
  if (!document.getElementById('view-timeline').hidden) buildTimeline(true);
});
function projectLabel(n){
  if (n.ghost) return '幽灵泡泡';
  return n.project || '自由泡泡';
}
function matchesProject(n){
  if (!activeProject) return true;
  if (activeProject === '__free__') return !n.project && !n.ghost;
  return n.project === activeProject;
}
function matchesQuery(n){
  if (!query) return true;
  return n.id.toLowerCase().includes(query)
    || n.topics.some(t=>t.toLowerCase().includes(query))
    || String(n.project || '').toLowerCase().includes(query)
    || String(n.path || '').toLowerCase().includes(query)
    || n.html.toLowerCase().includes(query);
}
function isVisibleNode(n){
  return matchesProject(n) && matchesQuery(n);
}

// ---------- 导出 ----------
const exportBox = document.getElementById('export');
const exportToggle = document.getElementById('export-toggle');
const exportStatus = document.getElementById('export-status');
exportToggle.addEventListener('click', e => {
  e.stopPropagation();
  exportBox.classList.toggle('open');
  exportToggle.setAttribute('aria-expanded', exportBox.classList.contains('open') ? 'true' : 'false');
});
document.addEventListener('click', e => {
  if (!exportBox.contains(e.target)) {
    exportBox.classList.remove('open');
    exportToggle.setAttribute('aria-expanded', 'false');
  }
});
function stamp(){
  const d = new Date();
  return d.getFullYear() + String(d.getMonth()+1).padStart(2,'0') + String(d.getDate()).padStart(2,'0');
}
function downloadFile(name, text, type){
  if (exportStatus) exportStatus.textContent = '正在生成 ' + name;
  const blob = new Blob([text], {type});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  showCopyToast('已开始导出');
  if (exportStatus) exportStatus.textContent = '已开始下载: ' + name;
  setTimeout(()=>URL.revokeObjectURL(url), 1000);
}
async function serverExport(type){
  if (exportStatus) exportStatus.textContent = '正在写入本地文件...';
  const res = await fetch('/api/export', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({type})
  });
  let data = {};
  try { data = await res.json(); } catch (_) {}
  if (!res.ok || data.ok === false) throw new Error(data.error || '导出失败');
  if (exportStatus) {
    exportStatus.innerHTML = '已保存: <a href="'+escAttr(data.url)+'" target="_blank">'+escHtml(data.path || data.filename)+'</a>';
  }
  showCopyToast('已导出到本地');
  return data;
}
function csvCell(value){
  return '"' + String(value ?? '').replace(/"/g, '""').replace(/\r?\n/g, ' / ') + '"';
}
function exportMarkdown(){
  const real = N.filter(n=>!n.ghost).sort((a,b)=>String(a.created_at || a.date || '').localeCompare(String(b.created_at || b.date || '')) || a.id.localeCompare(b.id));
  const lines = [
    '# 灵感泡泡导出',
    '',
    '- 导出时间: ' + DATA.generated,
    '- 泡泡数: ' + real.length,
    '- 关联数: ' + E.length,
    '',
    '> Obsidian 最完整的源文件就是泡泡库里的每个 `.md` 文件;这个文件是给其他软件预览和迁移用的索引版。',
    ''
  ];
  real.forEach(n=>{
    lines.push('## ' + n.id);
    if (n.date) lines.push('', '- 日期: ' + n.date);
    if (n.created_at) lines.push('- 时间戳: ' + n.created_at);
    lines.push('- 项目: ' + projectLabel(n));
    if (n.path) lines.push('- 文件: ' + n.path);
    if (n.topics.length) lines.push('- 主题: ' + n.topics.join(', '));
    if (n.links.length) lines.push('- 关联: ' + n.links.map(x=>'[['+x+']]').join('、'));
    lines.push('', n.body.trim() || '(空)', '');
    if (n.suggestions && n.suggestions.length) {
      lines.push('### 继续聊聊', '');
      n.suggestions.forEach(s=>lines.push('- ' + s));
      lines.push('');
    }
  });
  downloadFile('灵感泡泡导出-' + stamp() + '.md', lines.join('\n'), 'text/markdown;charset=utf-8');
}
function exportJson(){
  const payload = {
    generated: DATA.generated,
    bubbles: N.map(n=>({
      title: n.id,
      date: n.date,
      created_at: n.created_at || null,
      project: n.project || null,
      path: n.path || null,
      topics: n.topics,
      body: n.body,
      links: n.links,
      suggestions: n.suggestions || [],
      ghost: n.ghost
    })),
    edges: E.map(([a,b])=>({source: N[a].id, target: N[b].id}))
  };
  downloadFile('灵感泡泡数据-' + stamp() + '.json', JSON.stringify(payload, null, 2), 'application/json;charset=utf-8');
}
function exportCsv(){
  const rows = [['title','date','created_at','project','path','topics','links','suggestions','ghost','body']];
  N.forEach(n=>rows.push([n.id, n.date || '', n.created_at || '', n.project || '', n.path || '', n.topics.join('|'), n.links.join('|'), (n.suggestions || []).join('|'), n.ghost ? 'true' : 'false', n.body]));
  downloadFile('灵感泡泡表格-' + stamp() + '.csv', rows.map(r=>r.map(csvCell).join(',')).join('\n'), 'text/csv;charset=utf-8');
}
function exportHarvest(){
  const real = N.filter(n=>!n.ghost);
  const byFreshness = real.slice().sort((a,b)=>
    String(b.created_at || b.date || '').localeCompare(String(a.created_at || a.date || '')) || b.idx - a.idx
  );
  const newestDate = byFreshness.map(n=>n.date).filter(Boolean).sort().pop();
  let recent = byFreshness.slice(0, 12);
  if (newestDate) {
    const end = new Date(newestDate + 'T00:00:00');
    const start = new Date(end);
    start.setDate(start.getDate() - 6);
    const recentByDate = byFreshness.filter(n=>{
      if (!n.date) return false;
      const d = new Date(n.date + 'T00:00:00');
      return d >= start && d <= end;
    });
    if (recentByDate.length) recent = recentByDate;
  }

  const topicCount = new Map();
  real.forEach(n=>n.topics.forEach(t=>topicCount.set(t, (topicCount.get(t) || 0) + 1)));
  const hotTopics = [...topicCount.entries()]
    .sort((a,b)=>b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 10);
  const connected = real.slice()
    .sort((a,b)=>b.degree - a.degree || String(b.created_at || b.date || '').localeCompare(String(a.created_at || a.date || '')))
    .slice(0, 8);
  const ghosts = N.filter(n=>n.ghost).slice(0, 10);

  const pool = [...connected, ...recent].filter((n, i, arr)=>arr.findIndex(x=>x.id === n.id) === i);
  const seenPairs = new Set();
  const combos = [];
  for (let i = 0; i < pool.length; i++) {
    for (let j = i + 1; j < pool.length; j++) {
      const a = pool[i], b = pool[j];
      const key = [a.id, b.id].sort().join('::');
      if (seenPairs.has(key)) continue;
      const sharedTopic = a.topics.find(t=>b.topics.includes(t));
      const linked = a.links.includes(b.id) || b.links.includes(a.id);
      if (!sharedTopic && !linked) continue;
      seenPairs.add(key);
      combos.push({a, b, reason: sharedTopic ? '共同主题: ' + sharedTopic : '已有双链关联'});
      if (combos.length >= 6) break;
    }
    if (combos.length >= 6) break;
  }
  if (!combos.length && byFreshness.length >= 2) {
    combos.push({a: byFreshness[0], b: byFreshness[1], reason: '最近相邻出现'});
  }

  const lines = [
    '# 灵感收成',
    '',
    '- 生成时间: ' + DATA.generated,
    '- 泡泡数: ' + real.length,
    '- 关联数: ' + E.length,
    '',
    '> 这是一份临时视图,不改变任何泡泡文件。项目只是可选视角;真正的底层结构还是泡泡之间的双链和主题气味。',
    '',
    '## 最近新增',
    ''
  ];
  (recent.length ? recent : []).forEach(n=>{
    const meta = [n.date, n.topics.join(', ')].filter(Boolean).join(' · ');
    lines.push('- [[' + n.id + ']]' + (meta ? ' - ' + meta : ''));
  });
  if (!recent.length) lines.push('- 暂时没有可统计的新增泡泡。');

  lines.push('', '## 热门主题', '');
  hotTopics.forEach(([topic, count])=>lines.push('- ' + topic + ': ' + count + ' 个泡泡'));
  if (!hotTopics.length) lines.push('- 暂时没有主题标签。');

  lines.push('', '## 连接最多的泡泡', '');
  connected.forEach(n=>lines.push('- [[' + n.id + ']] - ' + n.degree + ' 条连接'));
  if (!connected.length) lines.push('- 暂时没有可统计的连接。');

  lines.push('', '## 可以展开的幽灵泡泡', '');
  ghosts.forEach(n=>lines.push('- [[' + n.id + ']]'));
  if (!ghosts.length) lines.push('- 暂时没有幽灵泡泡。');

  lines.push('', '## 组合发散', '');
  combos.forEach(({a,b,reason})=>{
    lines.push('- 把 [[' + a.id + ']] 和 [[' + b.id + ']] 碰一碰(' + reason + '): 它们能不能变成一个更小、更可验证的新实验?');
  });
  if (!combos.length) lines.push('- 暂时没有足够的泡泡可以组合。');

  lines.push('', '## 反向问题', '');
  lines.push('- 最近这些想法里,哪一个最容易只是好玩但没有持续使用场景?');
  lines.push('- 哪一个想法可以用一天内的小实验验证,而不是先做完整产品?');
  lines.push('- 哪些泡泡不该被固定到项目里,反而应该继续自由漂移一阵?');

  downloadFile('灵感收成-' + stamp() + '.md', lines.join('\n'), 'text/markdown;charset=utf-8');
}
document.getElementById('export-menu').addEventListener('click', async e=>{
  const btn = e.target.closest('button[data-export]');
  if (!btn) return;
  e.stopPropagation();
  const type = btn.dataset.export;
  try {
    await serverExport(type);
  } catch (err) {
    if (exportStatus) exportStatus.textContent = (err.message || '服务端导出失败') + ', 改用浏览器下载。';
    if (type === 'markdown') exportMarkdown();
    if (type === 'harvest') exportHarvest();
    if (type === 'json') exportJson();
    if (type === 'csv') exportCsv();
  }
  setTimeout(()=>{
    exportBox.classList.remove('open');
    exportToggle.setAttribute('aria-expanded', 'false');
  }, 1200);
});

// ---------- 详情面板 ----------
const panel = document.getElementById('panel');
let selected = null;
function openPanel(n){
  selected = n;
  document.getElementById('p-title').textContent = n.id;
  document.getElementById('p-meta').innerHTML =
    (n.created_at ? '<span>'+n.created_at+'</span>' : (n.date ? '<span>'+n.date+'</span>' : '<span>幽灵泡泡</span>')) +
    '<span>' + projectLabel(n) + '</span>' +
    (n.path ? '<span>' + escHtml(n.path) + '</span>' : '') +
    n.topics.map(t=>'<span class="chip" style="border-color:'+topicColor[t]+';color:'+topicColor[t]+'">'+t+'</span>').join('');
  document.getElementById('p-body').innerHTML = n.html;
  const ideas = n.suggestions || [];
  document.getElementById('p-ideas').innerHTML = ideas.length
    ? '<h3>继续聊聊</h3><div class="idea-list">' + ideas.map(s=>'<button class="idea-btn" type="button" data-suggestion="'+s.replace(/"/g,'&quot;')+'">'+s+'</button>').join('') + '</div><div class="copy-tip" id="copy-tip">点一下复制话题,拿去继续聊。</div>'
    : '';
  const nbrs = [];
  E.forEach(([a,b])=>{ if(a===n.idx) nbrs.push(N[b]); else if(b===n.idx) nbrs.push(N[a]); });
  document.getElementById('p-links').innerHTML = nbrs.length
    ? '<h3>关联泡泡</h3>' + nbrs.map(m=>'<div><a class="wl" data-id="'+m.id.replace(/"/g,'&quot;')+'">'+m.id+'</a></div>').join('')
    : '';
  panel.classList.add('open');
  if (homeIdeas.classList.contains('open')) renderHomeIdeas(n);
  draw();
}
document.getElementById('panel-close').onclick = ()=>{ panel.classList.remove('open'); selected=null; draw(); };
function fallbackCopy(text){
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.setAttribute('readonly', '');
  ta.style.position = 'fixed';
  ta.style.left = '-9999px';
  ta.style.top = '0';
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  let ok = false;
  try { ok = document.execCommand('copy'); } catch (_) { ok = false; }
  ta.remove();
  return ok;
}
let toastTimer = null;
function showCopyToast(message){
  const toast = document.getElementById('copy-toast');
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(()=>toast.classList.remove('show'), 1600);
}
async function copyIdea(text, tip){
  let ok = false;
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch (_) {
      ok = false;
    }
  }
  if (!ok) ok = fallbackCopy(text);
  const message = ok ? '已复制,可以直接粘贴继续聊。' : '复制被浏览器拦住了,话题如下: ' + text;
  if (tip) tip.textContent = message;
  showCopyToast(ok ? '已复制' : '复制失败');
}
document.addEventListener('click', e=>{
  const idea = e.target.closest('.idea-btn');
  if (idea) {
    const text = idea.dataset.suggestion || idea.textContent.trim();
    const tip = idea.closest('.ideas, .home-ideas')?.querySelector('.copy-tip');
    copyIdea(text, tip);
    return;
  }
  const a = e.target.closest('a.wl');
  if (a && byId[a.dataset.id]) { openPanel(byId[a.dataset.id]); centerOn(byId[a.dataset.id]); }
});

// ---------- 主页面继续聊聊 ----------
const ideaLauncher = document.getElementById('idea-launcher');
const homeIdeas = document.getElementById('home-ideas');
const homeIdeasSource = document.getElementById('home-ideas-source');
const homeIdeasList = document.getElementById('home-ideas-list');
const ideaSources = N.filter(n=>!n.ghost && n.suggestions && n.suggestions.length)
  .sort((a,b)=>String(b.created_at || b.date || '').localeCompare(String(a.created_at || a.date || '')) || b.idx - a.idx);
let ideaSourceIndex = 0;
let currentIdeaSource = null;
function escAttr(s){ return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function escHtml(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function randomIdeaSource(except){
  if (!ideaSources.length) return null;
  const pool = ideaSources.length > 1 && except ? ideaSources.filter(n=>n!==except) : ideaSources;
  return pool[Math.floor(Math.random() * pool.length)];
}
function renderHomeIdeas(source){
  if (!source || !source.suggestions || !source.suggestions.length) {
    homeIdeas.hidden = true;
    ideaLauncher.hidden = true;
    return;
  }
  currentIdeaSource = source;
  homeIdeas.hidden = false;
  ideaLauncher.hidden = false;
  homeIdeasSource.textContent = '从「' + source.id + '」发散';
  homeIdeasList.innerHTML = source.suggestions.map(s=>
    '<button class="idea-btn" type="button" data-suggestion="'+escAttr(s)+'">'+escHtml(s)+'</button>'
  ).join('');
}
if (!ideaSources.length) ideaLauncher.hidden = true;
ideaLauncher.addEventListener('click', () => {
  renderHomeIdeas(randomIdeaSource(currentIdeaSource));
  homeIdeas.classList.add('open');
  ideaLauncher.hidden = true;
});
document.getElementById('close-ideas').addEventListener('click', () => {
  homeIdeas.classList.remove('open');
  if (ideaSources.length) ideaLauncher.hidden = false;
});
document.getElementById('cycle-ideas').addEventListener('click', e=>{
  e.stopPropagation();
  if (!ideaSources.length) return;
  renderHomeIdeas(randomIdeaSource(currentIdeaSource));
});

// ---------- 力导向图 ----------
const cv = document.getElementById('cv');
const ctx = cv.getContext('2d');
let W=0, H=0, dpr=1;
function resize(){
  dpr = window.devicePixelRatio||1;
  W = cv.clientWidth; H = cv.clientHeight;
  cv.width = W*dpr; cv.height = H*dpr;
  draw();
}
window.addEventListener('resize', resize);

N.forEach((n,i)=>{
  const a = i*2.399963, r = 30*Math.sqrt(i+1);
  n.x = Math.cos(a)*r; n.y = Math.sin(a)*r;
  n.vx=0; n.vy=0; n.fixed=false;
});
let alpha = 1;
const view = { x:0, y:0, k:1 };   // 世界原点在画布中心,再加偏移和缩放

function tick(){
  if (alpha > 0.003 && N.length) {
    alpha *= 0.985;
    const rep = 3600, spring = 0.03, len = 135, grav = 0.008;
    for (let i=0;i<N.length;i++){
      for (let j=i+1;j<N.length;j++){
        const a=N[i], b=N[j];
        let dx=b.x-a.x, dy=b.y-a.y;
        let d2 = dx*dx+dy*dy || 1;
        if (d2 < 360000) {
          const f = rep/d2 * alpha;
          const d = Math.sqrt(d2);
          dx/=d; dy/=d;
          a.vx -= dx*f; a.vy -= dy*f;
          b.vx += dx*f; b.vy += dy*f;
        }
      }
    }
    E.forEach(([ia,ib])=>{
      const a=N[ia], b=N[ib];
      const dx=b.x-a.x, dy=b.y-a.y;
      const d = Math.sqrt(dx*dx+dy*dy)||1;
      const f = spring*(d-len)*alpha;
      a.vx += dx/d*f; a.vy += dy/d*f;
      b.vx -= dx/d*f; b.vy -= dy/d*f;
    });
    N.forEach(n=>{
      n.vx -= n.x*grav*alpha; n.vy -= n.y*grav*alpha;
      if (!n.fixed){ n.x += n.vx; n.y += n.vy; }
      n.vx *= 0.85; n.vy *= 0.85;
    });
    draw();
  }
  requestAnimationFrame(tick);
}

function toScreen(p){ return { x: W/2 + (p.x+view.x)*view.k, y: H/2 + (p.y+view.y)*view.k }; }
function toWorld(sx,sy){ return { x:(sx-W/2)/view.k - view.x, y:(sy-H/2)/view.k - view.y }; }

function draw(){
  ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.clearRect(0,0,W,H);
  const nbr = new Set();
  if (selected) E.forEach(([a,b])=>{
    if(a===selected.idx){nbr.add(b);} if(b===selected.idx){nbr.add(a);}
  });
  const visible = new Set(N.filter(isVisibleNode).map(n=>n.idx));
  const qHits = query ? new Set(N.filter(n=>matchesProject(n) && matchesQuery(n)).map(n=>n.idx)) : null;
  ctx.lineWidth = 1;
  E.forEach(([ia,ib])=>{
    if (!visible.has(ia) || !visible.has(ib)) return;
    const a=toScreen(N[ia]), b=toScreen(N[ib]);
    const hot = selected && (ia===selected.idx || ib===selected.idx);
    const queryHot = qHits && (qHits.has(ia) || qHits.has(ib));
    ctx.strokeStyle = hot ? 'rgba(17,17,17,.72)' : (queryHot ? 'rgba(17,17,17,.32)' : 'rgba(31,31,31,'+(selected || qHits?'.10':'.20')+')');
    ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.stroke();
  });
  N.forEach(n=>{
    if (!visible.has(n.idx)) return;
    const p = toScreen(n);
    const dimmed = selected && n!==selected && !nbr.has(n.idx);
    const queryDim = qHits && !qHits.has(n.idx);
    ctx.globalAlpha = (dimmed || queryDim) ? 0.25 : 1;
    ctx.beginPath();
    ctx.arc(p.x, p.y, n.r*Math.min(view.k,1.6) + 6, 0, 7);
    ctx.fillStyle = n.ghost ? 'rgba(31,31,31,.06)' : 'rgba(31,31,31,.06)';
    ctx.fill();
    ctx.beginPath();
    ctx.arc(p.x, p.y, n.r*Math.min(view.k,1.6), 0, 7);
    ctx.fillStyle = n.color;
    if (n.ghost){ ctx.setLineDash([3,3]); ctx.strokeStyle=GHOST; ctx.lineWidth=1.2; ctx.stroke(); ctx.setLineDash([]);
      ctx.globalAlpha *= .5; ctx.fill(); ctx.globalAlpha = (dimmed || queryDim)?0.25:1; }
    else ctx.fill();
    if (n===selected || (qHits && qHits.has(n.idx))){
      ctx.strokeStyle='rgba(255,255,255,.98)';
      ctx.lineWidth=3;
      ctx.stroke();
      ctx.strokeStyle='rgba(17,17,17,.62)';
      ctx.lineWidth=1.2;
      ctx.stroke();
    }
    if (view.k > 0.45 || n===selected || nbr.has(n.idx) || (qHits && qHits.has(n.idx))){
      ctx.fillStyle = (dimmed || queryDim) ? 'rgba(31,31,31,.34)' : '#1f1f1f';
      ctx.font = '12px -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif';
      ctx.textAlign='center';
      ctx.fillText(n.id, p.x, p.y + n.r*Math.min(view.k,1.6) + 13);
    }
    ctx.globalAlpha = 1;
  });
}

function hit(sx,sy){
  for (let i=N.length-1;i>=0;i--){
    if (!isVisibleNode(N[i])) continue;
    const p = toScreen(N[i]);
    const r = N[i].r*Math.min(view.k,1.6)+5;
    if ((sx-p.x)**2+(sy-p.y)**2 < r*r) return N[i];
  }
  return null;
}
function centerOn(n){
  if (n.x===undefined) return;
  view.x = -n.x; view.y = -n.y;
  draw();
}

let dragNode=null, panning=false, last=null, moved=false;
cv.addEventListener('mousedown', e=>{
  const n = hit(e.offsetX, e.offsetY);
  moved=false; last={x:e.offsetX,y:e.offsetY};
  if (n){ dragNode=n; n.fixed=true; }
  else panning=true;
});
window.addEventListener('mousemove', e=>{
  if(!last) return;
  const r = cv.getBoundingClientRect();
  const sx = e.clientX-r.left, sy=e.clientY-r.top;
  const dx = sx-last.x, dy = sy-last.y;
  if (Math.abs(dx)+Math.abs(dy)>2) moved=true;
  if (dragNode){
    const w = toWorld(sx,sy);
    dragNode.x=w.x; dragNode.y=w.y; alpha=Math.max(alpha,0.25); draw();
  } else if (panning){
    view.x += dx/view.k; view.y += dy/view.k; draw();
  }
  last={x:sx,y:sy};
});
window.addEventListener('mouseup', e=>{
  if (dragNode){ dragNode.fixed=false; if(!moved) openPanel(dragNode); }
  else if (panning && !moved && e.target===cv){ panel.classList.remove('open'); selected=null; draw(); }
  dragNode=null; panning=false; last=null;
});
cv.addEventListener('wheel', e=>{
  e.preventDefault();
  const before = toWorld(e.offsetX, e.offsetY);
  view.k = Math.min(4, Math.max(0.15, view.k * Math.exp(-e.deltaY*0.0015)));
  const after = toWorld(e.offsetX, e.offsetY);
  view.x += after.x-before.x; view.y += after.y-before.y;
  draw();
}, {passive:false});

// ---------- 时间线 ----------
let tlBuilt = false;
function buildTimeline(force=false){
  if (tlBuilt && !force) return; tlBuilt = true;
  const wrap = document.getElementById('view-timeline');
  const dated = N.filter(n=>n.date && isVisibleNode(n));
  if (!dated.length){ wrap.innerHTML='<div style="padding:60px;color:var(--dim)">还没有泡泡</div>'; return; }
  const timelineDays = [...new Set(dated.map(n=>n.date))].sort();
  const cols = {};
  timelineDays.forEach((d,i)=>cols[d]=i);
  const stack = timelineDays.map(()=>0);
  const colW=170, rowH=64, top=80, leftPad=60;
  dated.forEach(n=>{
    const c = cols[n.date];
    n.tx = leftPad + c*colW + colW/2;
    n.ty = top + (stack[c]++)*rowH + 40;
  });
  const width = leftPad*2 + timelineDays.length*colW;
  const height = top + Math.max(...stack, 1)*rowH + 80;
  let svg = '<svg id="tl" width="'+width+'" height="'+height+'" xmlns="http://www.w3.org/2000/svg">';
  // 列标题和分隔
  timelineDays.forEach((d,i)=>{
    const x = leftPad + i*colW + colW/2;
    svg += '<text x="'+x+'" y="34" text-anchor="middle" fill="#77746b" font-size="12">'+d+'</text>';
    if (i) svg += '<line x1="'+(leftPad+i*colW)+'" y1="50" x2="'+(leftPad+i*colW)+'" y2="'+(height-20)+'" stroke="rgba(32,32,29,.12)" stroke-dasharray="2,5"/>';
  });
  // 弧线
  E.forEach(([ia,ib])=>{
    if (!isVisibleNode(N[ia]) || !isVisibleNode(N[ib])) return;
    const a=N[ia], b=N[ib];
    if (a.tx===undefined || b.tx===undefined) return;
    if (a.date===b.date){
      const x=a.tx, y1=Math.min(a.ty,b.ty), y2=Math.max(a.ty,b.ty);
      svg += '<path d="M '+x+' '+y1+' C '+(x-46)+' '+y1+', '+(x-46)+' '+y2+', '+x+' '+y2+'" fill="none" stroke="rgba(31,31,31,.18)"/>';
    } else {
      const [l,r2] = a.tx<b.tx ? [a,b] : [b,a];
      const mx=(l.tx+r2.tx)/2, my=Math.min(l.ty,r2.ty)-34;
      svg += '<path d="M '+l.tx+' '+l.ty+' Q '+mx+' '+my+', '+r2.tx+' '+r2.ty+'" fill="none" stroke="rgba(17,17,17,.30)" stroke-width="1.2"/>';
    }
  });
  // 节点
  dated.forEach(n=>{
    const label = n.id.length>10 ? n.id.slice(0,10)+'…' : n.id;
    svg += '<g class="tl-node" data-idx="'+n.idx+'" style="cursor:pointer">'
      + '<circle cx="'+n.tx+'" cy="'+n.ty+'" r="'+Math.min(n.r,13)+'" fill="'+n.color+'"/>'
      + '<text x="'+n.tx+'" y="'+(n.ty+Math.min(n.r,13)+15)+'" text-anchor="middle" fill="#1f1f1f" font-size="11">'
      + label.replace(/&/g,'&amp;').replace(/</g,'&lt;') + '</text></g>';
  });
  svg += '</svg>';
  wrap.innerHTML = svg;
  wrap.querySelectorAll('.tl-node').forEach(g=>{
    g.addEventListener('click', ()=>openPanel(N[+g.dataset.idx]));
  });
}

// ---------- 标签切换 ----------
const vg = document.getElementById('view-graph'), vt = document.getElementById('view-timeline');
const tg = document.getElementById('tab-graph'), tt = document.getElementById('tab-timeline');
tg.onclick = ()=>{ vg.hidden=false; vt.hidden=true; tg.classList.add('on'); tt.classList.remove('on'); resize(); };
tt.onclick = ()=>{ vg.hidden=true; vt.hidden=false; tt.classList.add('on'); tg.classList.remove('on'); buildTimeline(); };

resize();
tick();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="生成灵感泡泡图谱")
    ap.add_argument("vault", nargs="?", default=str(Path.home() / "灵感泡泡"))
    ap.add_argument("-o", "--output", default=None)
    args = ap.parse_args()

    vault = Path(args.vault).expanduser()
    vault.mkdir(parents=True, exist_ok=True)
    out = Path(args.output) if args.output else vault / "图谱.html"
    data = write_graph(vault, out)

    real = sum(1 for n in data["nodes"] if not n["ghost"])
    ghosts = len(data["nodes"]) - real
    day_count = len({n["date"] for n in data["nodes"] if n["date"]})
    print(f"🫧 {real} 个泡泡(+{ghosts} 个幽灵) · {len(data['edges'])} 条关联 · 跨 {day_count} 天")
    print(f"图谱已生成:{out}")


if __name__ == "__main__":
    main()
