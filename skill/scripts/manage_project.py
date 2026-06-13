#!/usr/bin/env python3
"""Manage 灵感泡泡 project folders.

Projects are lightweight folders under the bubble vault. Bubble notes inside a
project folder still use ordinary Markdown files and [[double links]].
"""

import argparse
import re
import sys
from pathlib import Path

INVALID_CHARS = set('/\\:*?"<>|')


def clean_name(name):
    name = re.sub(r"\s+", " ", name.strip())
    if not name:
        raise ValueError("项目名不能为空")
    if name in {".", ".."} or any(ch in INVALID_CHARS for ch in name):
        raise ValueError('项目名不能包含 / \\ : * ? " < > |')
    if "/" in name or "\\" in name:
        raise ValueError("项目名只能是一层文件夹名")
    return name


def project_path(vault, name):
    return vault / clean_name(name)


def create_project(vault, name):
    path = project_path(vault, name)
    if path.exists():
        raise FileExistsError(f"项目已存在: {path.name}")
    path.mkdir(parents=False)
    return path


def rename_project(vault, old_name, new_name):
    old_path = project_path(vault, old_name)
    new_path = project_path(vault, new_name)
    if not old_path.is_dir():
        raise FileNotFoundError(f"项目不存在: {old_path.name}")
    if new_path.exists():
        raise FileExistsError(f"目标项目已存在: {new_path.name}")
    old_path.rename(new_path)
    return new_path


def main():
    ap = argparse.ArgumentParser(description="新建或改名灵感泡泡项目文件夹")
    ap.add_argument("action", choices=["create", "rename"])
    ap.add_argument("name")
    ap.add_argument("new_name", nargs="?")
    ap.add_argument("--vault", default=".")
    args = ap.parse_args()

    vault = Path(args.vault).expanduser().resolve()
    vault.mkdir(parents=True, exist_ok=True)

    try:
        if args.action == "create":
            path = create_project(vault, args.name)
            print(f"已新建项目: {path.name}")
            print(f"项目文件夹: {path}")
        else:
            if not args.new_name:
                raise ValueError("改名需要提供新项目名")
            path = rename_project(vault, args.name, args.new_name)
            print(f"已改名项目: {args.name} -> {path.name}")
            print(f"项目文件夹: {path}")
    except (ValueError, FileExistsError, FileNotFoundError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
