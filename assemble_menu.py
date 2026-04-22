#!/usr/bin/env python3
"""Assemble a task-info JSON by resolving its menu snippets locally.

Lets the user pick a task-info-*.json file, reads it, then rebuilds the
`menu` array from snippet files in the sibling `menue-snippets` repo.
The resulting file is written to `assembled-menues/<stem>/<name>.json`.
"""
from __future__ import annotations

import json
import re
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
TASK_INFO_DIR = SCRIPT_DIR
SNIPPETS_DIR = SCRIPT_DIR.parent / "menue-snippets"
OUTPUT_ROOT = SCRIPT_DIR / "assembled-menues"

URL_RE = re.compile(
    r"^https?://api\.github\.com/repos/[^/]+/menue-snippets/contents/"
    r"(?P<path>.+?)(?:\?.*)?$"
)


def url_to_local_path(url: str) -> Path:
    match = URL_RE.match(url)
    if not match:
        raise ValueError(f"Unsupported snippet URL: {url}")
    return SNIPPETS_DIR / match.group("path")


def load_snippet(url: str) -> dict:
    path = url_to_local_path(url)
    if not path.is_file():
        raise FileNotFoundError(f"Snippet not found: {path}")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh, object_pairs_hook=OrderedDict)


def list_task_info_files(folder: Path = TASK_INFO_DIR) -> list[Path]:
    skip = {Path(__file__).name}
    return sorted(
        p for p in folder.glob("*.json") if p.name not in skip
    )


def resolve_selection(arg: str, files: list[Path]) -> Path | None:
    if arg.isdigit():
        idx = int(arg) - 1
        if 0 <= idx < len(files):
            return files[idx]
        return None
    candidate = Path(arg).expanduser()
    if not candidate.is_absolute():
        candidate = TASK_INFO_DIR / arg
    if candidate.suffix.lower() != ".json":
        candidate = candidate.with_suffix(".json")
    return candidate if candidate.is_file() else None


def navigate(container: dict, path: str) -> dict:
    current: Any = container
    for segment in (s for s in path.split("/") if s):
        if not isinstance(current, dict):
            raise ValueError(
                f"Cannot descend into non-object at segment '{segment}'"
            )
        if segment not in current:
            current[segment] = OrderedDict()
        current = current[segment]
    if not isinstance(current, dict):
        raise ValueError(f"Path '{path}' does not resolve to an object")
    return current


def merge_after(target: dict, incoming: dict, after_key: str) -> None:
    if after_key not in target:
        target.update(incoming)
        return
    rebuilt: OrderedDict = OrderedDict()
    for key, value in target.items():
        if key in incoming:
            continue
        rebuilt[key] = value
        if key == after_key:
            for nk, nv in incoming.items():
                rebuilt[nk] = nv
    target.clear()
    target.update(rebuilt)


def merge_at_end(target: dict, incoming: dict) -> None:
    for key, value in incoming.items():
        target.pop(key, None)
        target[key] = value


def resolve_node(node: dict) -> dict:
    if "source" not in node:
        raise ValueError(f"Menu node missing 'source': {node}")
    content = load_snippet(node["source"])

    for child in node.get("children", []) or []:
        child_content = resolve_node(child)
        target = navigate(content, child.get("property", ""))
        after = child.get("after")
        if after:
            merge_after(target, child_content, after)
        else:
            merge_at_end(target, child_content)

    return content


def assemble_menu(task_info: dict) -> list:
    return [resolve_node(item) for item in task_info.get("menu", [])]


def assemble_one(path: Path) -> Path:
    with path.open(encoding="utf-8") as fh:
        task_info = json.load(fh, object_pairs_hook=OrderedDict)
    task_info["menu"] = assemble_menu(task_info)

    out_dir = OUTPUT_ROOT / path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / path.name
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(task_info, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return out_path


def run_batch(folder: Path) -> int:
    folder = folder.expanduser().resolve()
    if not folder.is_dir():
        sys.exit(f"Not a directory: {folder}")
    files = list_task_info_files(folder)
    if not files:
        sys.exit(f"No .json files found in {folder}")

    print(f"Batch assembling {len(files)} file(s) from {folder}\n")
    failures: list[tuple[str, Exception]] = []
    for p in files:
        try:
            out = assemble_one(p)
            print(f"  OK   {p.name} -> {out}")
        except Exception as err:
            failures.append((p.name, err))
            print(f"  FAIL {p.name}: {err}")

    print()
    if failures:
        print(f"Completed with {len(failures)} failure(s) of {len(files)}.")
        return 1
    print(f"Completed: {len(files)} file(s) assembled.")
    return 0


def run_single(path: Path) -> None:
    print(f"\nAssembling: {path.name}")
    out_path = assemble_one(path)
    print(f"Wrote: {out_path}")


def interactive() -> int:
    files = list_task_info_files()
    if not files:
        sys.exit("No task-info JSON files found.")

    width = len(str(len(files)))
    print(f"Available task-info files in {TASK_INFO_DIR}:\n")
    for i, p in enumerate(files, 1):
        print(f"  {str(i).rjust(width)}. {p.name}")
    print(f"\n  {'a'.rjust(width)}. [batch-run all files in a folder]")
    print()
    choice = input(
        "Select by number, filename, or 'a [folder]' for batch: "
    ).strip()
    if not choice:
        sys.exit("No selection made.")

    if choice.lower() == "a" or choice.lower().startswith(("a ", "all ", "batch ")):
        rest = choice.split(None, 1)
        folder = Path(rest[1]).expanduser() if len(rest) > 1 else TASK_INFO_DIR
        return run_batch(folder)

    selected = resolve_selection(choice, files)
    if selected is None:
        sys.exit(f"Invalid selection: {choice}")
    run_single(selected)
    return 0


def main() -> int:
    args = sys.argv[1:]

    if args and args[0] in {"--batch", "-b", "--all"}:
        folder = Path(args[1]) if len(args) > 1 else TASK_INFO_DIR
        return run_batch(folder)

    if len(args) == 1:
        candidate = Path(args[0]).expanduser()
        if candidate.is_dir():
            return run_batch(candidate)
        files = list_task_info_files()
        selected = resolve_selection(args[0], files)
        if selected is None:
            sys.exit(f"Could not resolve selection: {args[0]}")
        run_single(selected)
        return 0

    if args:
        sys.exit(
            "Usage: assemble_menu.py [<file|index>|<folder>|--batch [folder]]"
        )

    return interactive()


if __name__ == "__main__":
    sys.exit(main())
