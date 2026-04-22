#!/usr/bin/env python3
"""Remove input-section references from task-info menu entries.

Walks `menu` recursively in every task-info/*.json file and drops any node
whose `property` targets the input fieldset, or whose snippet is pure input
(every top-level key is `input` or `input.*`). Mixed input+non-input
snippets don't exist in the current snippet set, so no post-assembly
cleanup is required.

Result stays compatible with assemble_menu.py.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TASK_INFO_DIR = SCRIPT_DIR
SNIPPETS_DIR = SCRIPT_DIR.parent / "menue-snippets"

URL_RE = re.compile(
    r"^https?://api\.github\.com/repos/[^/]+/menue-snippets/contents/"
    r"(?P<path>.+?)(?:\?.*)?$"
)

_snippet_cache: dict[Path, dict | None] = {}


def url_to_local_path(url: str) -> Path | None:
    m = URL_RE.match(url or "")
    return None if not m else SNIPPETS_DIR / m.group("path")


def load_snippet(url: str) -> dict | None:
    path = url_to_local_path(url)
    if path is None:
        return None
    if path not in _snippet_cache:
        try:
            with path.open(encoding="utf-8") as fh:
                _snippet_cache[path] = json.load(fh)
        except (OSError, json.JSONDecodeError):
            _snippet_cache[path] = None
    return _snippet_cache[path]


def is_input_key(key: str) -> bool:
    return key == "input" or key.startswith("input.")


def is_pure_input_snippet(source: str) -> bool:
    data = load_snippet(source)
    if not isinstance(data, dict) or not data:
        return False
    return all(is_input_key(k) for k in data.keys())


def is_input_property(prop: str | None) -> bool:
    if not prop:
        return False
    head = prop.split("/", 1)[0]
    return is_input_key(head)


def count_removed(node: dict) -> int:
    total = 0
    for child in node.get("children") or []:
        total += 1 + count_removed(child)
    return total


def filter_node(node: dict) -> tuple[dict | None, int]:
    if not isinstance(node, dict):
        return node, 0
    if is_input_property(node.get("property")):
        return None, count_removed(node)
    if is_pure_input_snippet(node.get("source", "")):
        return None, count_removed(node)
    cleaned = dict(node)
    removed = 0
    children = node.get("children") or []
    if children:
        kept: list[dict] = []
        for child in children:
            fc, r = filter_node(child)
            removed += r
            if fc is None:
                removed += 1
            else:
                kept.append(fc)
        if kept:
            cleaned["children"] = kept
        else:
            cleaned.pop("children", None)
    return cleaned, removed


def strip_menu(task_info: dict) -> tuple[int, int]:
    menu = task_info.get("menu") or []
    if not isinstance(menu, list):
        return 0, 0
    new_menu: list[dict] = []
    top_dropped = 0
    total = 0
    for item in menu:
        fi, r = filter_node(item)
        total += r
        if fi is None:
            top_dropped += 1
            total += 1
        else:
            new_menu.append(fi)
    task_info["menu"] = new_menu
    return top_dropped, total


def main() -> int:
    files = sorted(p for p in TASK_INFO_DIR.glob("*.json"))
    if not files:
        sys.exit("No task-info JSON files found.")

    changed = 0
    unchanged = 0
    for path in files:
        try:
            original_text = path.read_text(encoding="utf-8")
            task_info = json.loads(original_text)
        except json.JSONDecodeError as err:
            print(f"  SKIP  {path.name}: {err}")
            continue
        if not isinstance(task_info, dict) or "menu" not in task_info:
            print(f"  SKIP  {path.name}: no menu section")
            continue

        top_dropped, total_dropped = strip_menu(task_info)
        new_text = json.dumps(task_info, indent=2, ensure_ascii=False) + "\n"
        if new_text != original_text:
            path.write_text(new_text, encoding="utf-8")
            changed += 1
            print(
                f"  UPD   {path.name}: dropped {total_dropped} node(s) "
                f"({top_dropped} top-level)"
            )
        else:
            unchanged += 1

    print(
        f"\n{changed} file(s) modified, {unchanged} unchanged "
        f"(of {len(files)} total)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
