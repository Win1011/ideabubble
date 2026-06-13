#!/usr/bin/env python3
"""Serve 灵感泡泡 graph with project-management APIs."""

import argparse
import csv
import datetime
import io
import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import build_graph
import manage_project

INVALID_TITLE_CHARS = set('/\\:*?"<>|')


def clean_list(value):
    if not value:
        return []
    if isinstance(value, str):
        value = [value]
    return [str(item).strip() for item in value if str(item).strip()]


def validate_title(title):
    title = str(title or "").strip()
    if not title:
        raise ValueError("标题不能为空")
    if title in {".", ".."}:
        raise ValueError("标题不能是特殊目录名")
    if any(ch in INVALID_TITLE_CHARS for ch in title):
        raise ValueError("标题包含不能用于文件名的字符")
    if len(title) > 60:
        raise ValueError("标题太长")
    return title


def validate_project(project):
    project = str(project or "").strip()
    if not project:
        return ""
    if "/" in project or "\\" in project or project in {".", ".."}:
        raise ValueError("项目名只能是一层文件夹名")
    if any(ch in INVALID_TITLE_CHARS for ch in project):
        raise ValueError("项目名包含不能用于文件名的字符")
    return project


def create_bubble(vault, payload):
    title = validate_title(payload.get("title"))
    project = validate_project(payload.get("project"))
    topics = clean_list(payload.get("topics")) or ["产品", "游戏"]
    links = clean_list(payload.get("links"))
    quotes = clean_list(payload.get("quotes"))
    body = str(payload.get("body") or "").strip()
    if not body:
        raise ValueError("内容不能为空")

    now = datetime.datetime.now().astimezone()
    target_dir = vault / project if project else vault
    target_dir.mkdir(parents=True, exist_ok=True)
    out = target_dir / f"{title}.md"
    if out.exists() and not payload.get("overwrite"):
        raise FileExistsError("同名泡泡已存在")

    lines = [
        "---",
        f"created: {now.date().isoformat()}",
        f"created_at: {now.isoformat(timespec='seconds')}",
        "topics: [" + ", ".join(topics) + "]",
        "---",
        "",
        body,
        "",
    ]
    if quotes:
        lines.append("原句:")
        lines.extend(f"> {quote}" for quote in quotes)
        lines.append("")
    if links:
        lines.append("关联:" + "、".join(f"[[{link}]]" for link in links))

    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return out


def stamp():
    return datetime.datetime.now().strftime("%Y%m%d")


def real_nodes(data):
    return [node for node in data["nodes"] if not node.get("ghost")]


def enrich_degrees(data):
    degrees = [0 for _ in data["nodes"]]
    for source, target in data["edges"]:
        degrees[source] += 1
        degrees[target] += 1
    for idx, node in enumerate(data["nodes"]):
        node["idx"] = idx
        node["degree"] = degrees[idx]
    return data


def project_label(node):
    if node.get("ghost"):
        return "幽灵泡泡"
    return node.get("project") or "自由泡泡"


def export_markdown(data):
    nodes = sorted(
        real_nodes(data),
        key=lambda n: (str(n.get("created_at") or n.get("date") or ""), n["id"]),
    )
    lines = [
        "# 灵感泡泡导出",
        "",
        f"- 导出时间: {data['generated']}",
        f"- 泡泡数: {len(nodes)}",
        f"- 关联数: {len(data['edges'])}",
        "",
        "> Obsidian 最完整的源文件就是泡泡库里的每个 `.md` 文件;这个文件是给其他软件预览和迁移用的索引版。",
        "",
    ]
    for node in nodes:
        lines.append(f"## {node['id']}")
        if node.get("date"):
            lines.extend(["", f"- 日期: {node['date']}"])
        if node.get("created_at"):
            lines.append(f"- 时间戳: {node['created_at']}")
        lines.append(f"- 项目: {project_label(node)}")
        if node.get("path"):
            lines.append(f"- 文件: {node['path']}")
        if node.get("topics"):
            lines.append("- 主题: " + ", ".join(node["topics"]))
        if node.get("links"):
            lines.append("- 关联: " + "、".join(f"[[{link}]]" for link in node["links"]))
        lines.extend(["", (node.get("body") or "").strip() or "(空)", ""])
        if node.get("suggestions"):
            lines.extend(["### 继续聊聊", ""])
            lines.extend(f"- {item}" for item in node["suggestions"])
            lines.append("")
    return "\n".join(lines), f"灵感泡泡导出-{stamp()}.md", "text/markdown;charset=utf-8"


def export_json(data):
    payload = {
        "generated": data["generated"],
        "bubbles": [
            {
                "title": node["id"],
                "date": node.get("date"),
                "created_at": node.get("created_at") or None,
                "project": node.get("project") or None,
                "path": node.get("path") or None,
                "topics": node.get("topics", []),
                "body": node.get("body", ""),
                "links": node.get("links", []),
                "suggestions": node.get("suggestions", []),
                "ghost": bool(node.get("ghost")),
            }
            for node in data["nodes"]
        ],
        "edges": [
            {"source": data["nodes"][source]["id"], "target": data["nodes"][target]["id"]}
            for source, target in data["edges"]
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2), f"灵感泡泡数据-{stamp()}.json", "application/json;charset=utf-8"


def export_csv(data):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["title", "date", "created_at", "project", "path", "topics", "links", "suggestions", "ghost", "body"])
    for node in data["nodes"]:
        writer.writerow([
            node["id"],
            node.get("date") or "",
            node.get("created_at") or "",
            node.get("project") or "",
            node.get("path") or "",
            "|".join(node.get("topics", [])),
            "|".join(node.get("links", [])),
            "|".join(node.get("suggestions", [])),
            "true" if node.get("ghost") else "false",
            node.get("body", ""),
        ])
    return buf.getvalue(), f"灵感泡泡表格-{stamp()}.csv", "text/csv;charset=utf-8"


def export_harvest(data):
    nodes = real_nodes(data)
    by_freshness = sorted(
        nodes,
        key=lambda n: (str(n.get("created_at") or n.get("date") or ""), n.get("idx", 0)),
        reverse=True,
    )
    recent = by_freshness[:12]
    topic_count = {}
    for node in nodes:
        for topic in node.get("topics", []):
            topic_count[topic] = topic_count.get(topic, 0) + 1
    hot_topics = sorted(topic_count.items(), key=lambda item: (-item[1], item[0]))[:10]
    connected = sorted(
        nodes,
        key=lambda n: (-int(n.get("degree", 0)), str(n.get("created_at") or n.get("date") or "")),
    )[:8]
    ghosts = [node for node in data["nodes"] if node.get("ghost")][:10]
    lines = [
        "# 灵感收成",
        "",
        f"- 生成时间: {data['generated']}",
        f"- 泡泡数: {len(nodes)}",
        f"- 关联数: {len(data['edges'])}",
        "",
        "> 这是一份临时视图,不改变任何泡泡文件。项目只是可选视角;真正的底层结构还是泡泡之间的双链和主题气味。",
        "",
        "## 最近新增",
        "",
    ]
    lines.extend(f"- [[{node['id']}]]" + (f" - {node['date']}" if node.get("date") else "") for node in recent)
    if not recent:
        lines.append("- 暂时没有可统计的新增泡泡。")
    lines.extend(["", "## 热门主题", ""])
    lines.extend(f"- {topic}: {count} 个泡泡" for topic, count in hot_topics)
    if not hot_topics:
        lines.append("- 暂时没有主题标签。")
    lines.extend(["", "## 连接最多的泡泡", ""])
    lines.extend(f"- [[{node['id']}]] - {node.get('degree', 0)} 条连接" for node in connected)
    if not connected:
        lines.append("- 暂时没有可统计的连接。")
    lines.extend(["", "## 可以展开的幽灵泡泡", ""])
    lines.extend(f"- [[{node['id']}]]" for node in ghosts)
    if not ghosts:
        lines.append("- 暂时没有幽灵泡泡。")
    return "\n".join(lines), f"灵感收成-{stamp()}.md", "text/markdown;charset=utf-8"


def make_export(data, export_type):
    if export_type == "markdown":
        return export_markdown(data)
    if export_type == "json":
        return export_json(data)
    if export_type == "csv":
        return export_csv(data)
    if export_type == "harvest":
        return export_harvest(data)
    raise ValueError("未知导出类型")


def make_handler(vault, output_name):
    class ProjectHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(vault), **kwargs)

        def send_json(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def read_json(self):
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            return json.loads(raw or "{}")

        def rebuild(self):
            build_graph.write_graph(vault, vault / output_name)

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/api/projects":
                data = build_graph.collect(vault)
                self.send_json(200, {"ok": True, "projects": data["projects"]})
                return
            super().do_GET()

        def do_POST(self):
            parsed = urlparse(self.path)
            try:
                payload = self.read_json()
                if parsed.path == "/api/projects":
                    manage_project.create_project(vault, payload.get("name", ""))
                    self.rebuild()
                    data = build_graph.collect(vault)
                    self.send_json(200, {"ok": True, "projects": data["projects"]})
                    return
                if parsed.path == "/api/projects/rename":
                    manage_project.rename_project(
                        vault,
                        payload.get("old_name", ""),
                        payload.get("new_name", ""),
                    )
                    self.rebuild()
                    data = build_graph.collect(vault)
                    self.send_json(200, {"ok": True, "projects": data["projects"]})
                    return
                if parsed.path == "/api/rebuild":
                    self.rebuild()
                    self.send_json(200, {"ok": True})
                    return
                if parsed.path == "/api/bubbles":
                    out = create_bubble(vault, payload)
                    self.rebuild()
                    self.send_json(200, {
                        "ok": True,
                        "title": out.stem,
                        "path": str(out),
                        "relative_path": out.relative_to(vault).as_posix(),
                    })
                    return
                if parsed.path == "/api/export":
                    data = enrich_degrees(build_graph.collect(vault))
                    text, filename, mime_type = make_export(data, payload.get("type", ""))
                    export_dir = vault / "导出"
                    export_dir.mkdir(exist_ok=True)
                    out = export_dir / filename
                    out.write_text(text, encoding="utf-8")
                    self.send_json(200, {
                        "ok": True,
                        "filename": filename,
                        "path": str(out),
                        "url": "/导出/" + filename,
                        "mime_type": mime_type,
                    })
                    return
                self.send_json(404, {"ok": False, "error": "未知接口"})
            except (ValueError, FileExistsError, FileNotFoundError, json.JSONDecodeError) as exc:
                self.send_json(400, {"ok": False, "error": str(exc)})

        def translate_path(self, path):
            parsed = urlparse(path)
            request_path = unquote(parsed.path)
            if request_path == "/":
                request_path = "/" + output_name
            return super().translate_path(request_path)

    return ProjectHandler


def main():
    ap = argparse.ArgumentParser(description="启动灵感泡泡图谱和项目管理服务")
    ap.add_argument("--vault", default=str(Path.home() / "灵感泡泡"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--output", default="图谱.html")
    args = ap.parse_args()

    vault = Path(args.vault).expanduser().resolve()
    vault.mkdir(parents=True, exist_ok=True)
    build_graph.write_graph(vault, vault / args.output)

    handler = make_handler(vault, args.output)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"灵感泡泡服务已启动: http://{args.host}:{args.port}/{args.output}")
    print(f"泡泡库: {vault}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止灵感泡泡服务", file=sys.stderr)


if __name__ == "__main__":
    main()
