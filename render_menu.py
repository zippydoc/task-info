#!/usr/bin/env python3
"""Render assembled task-info menus as interactive HTML pages.

Reads assembled JSON files under `assembled-menues/<stem>/<name>.json` and
emits an HTML page per file under `rendered-menues/<stem>/<name>.html`.
Shared JS/CSS assets are copied to `rendered-menues/assets/`, and a top-
level `rendered-menues/index.html` links to every rendered menu.

Usage:
  python3 render_menu.py                # interactive picker
  python3 render_menu.py <stem|path>    # render a single menu
  python3 render_menu.py --batch [dir]  # render every assembled menu
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ASSEMBLED_ROOT = SCRIPT_DIR / "assembled-menues"
OUTPUT_ROOT = SCRIPT_DIR / "rendered-menues"
FRAMEWORK_DIR = SCRIPT_DIR / "framework"
ASSETS_OUT = OUTPUT_ROOT / "assets"
ASSET_FILES = ("menu_render.js", "menu_render.css")


def list_assembled_files(root: Path = ASSEMBLED_ROOT) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(root.glob("*/*.json"))


def resolve_selection(arg: str, files: list[Path]) -> Path | None:
    if arg.isdigit():
        idx = int(arg) - 1
        return files[idx] if 0 <= idx < len(files) else None
    candidate = Path(arg).expanduser()
    if candidate.is_file():
        return candidate
    stem = arg[:-5] if arg.endswith(".json") else arg
    guess = ASSEMBLED_ROOT / stem / f"{stem}.json"
    return guess if guess.is_file() else None


def ensure_assets() -> None:
    ASSETS_OUT.mkdir(parents=True, exist_ok=True)
    for name in ASSET_FILES:
        src = FRAMEWORK_DIR / name
        if not src.is_file():
            sys.exit(f"Missing framework asset: {src}")
        shutil.copy2(src, ASSETS_OUT / name)


def html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<link rel="stylesheet" href="../assets/menu_render.css">
</head>
<body>
<header>
  <h1>{display_name}</h1>
  <p class="description">{description}</p>
  <a class="back" href="../index.html">&larr; back to index</a>
</header>
<main id="menu-root"></main>
<script id="task-data" type="application/json">{data}</script>
<script src="../assets/menu_render.js"></script>
<script>
  (function () {{
    var raw = document.getElementById("task-data").textContent;
    MenuRender.render(JSON.parse(raw), document.getElementById("menu-root"));
  }})();
</script>
</body>
</html>
"""


INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Rendered task-info menus</title>
<link rel="stylesheet" href="assets/menu_render.css">
</head>
<body>
<header>
  <h1>Rendered task-info menus</h1>
  <p class="description">{count} menus rendered from assembled-menues/</p>
</header>
<main>
  <ul class="menu-index">
{entries}
  </ul>
</main>
</body>
</html>
"""


def render_one(source: Path) -> Path:
    with source.open(encoding="utf-8") as fh:
        task_info = json.load(fh)

    stem = source.stem
    settings = task_info.get("scriptSettings") or {}
    display_name = settings.get("displayName") or stem
    description = task_info.get("description") or ""

    # Keep the embedded JSON safe inside <script>...</script>.
    data = json.dumps(task_info, ensure_ascii=False).replace("</", "<\\/")

    html = PAGE_TEMPLATE.format(
        title=html_escape(stem),
        display_name=html_escape(display_name),
        description=html_escape(description),
        data=data,
    )

    out_dir = OUTPUT_ROOT / stem
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{stem}.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path


def write_index(pages: list[Path]) -> Path:
    pages = sorted(pages)
    lines = []
    for p in pages:
        rel = p.relative_to(OUTPUT_ROOT).as_posix()
        lines.append(
            f'    <li><a href="{html_escape(rel)}">{html_escape(p.stem)}</a></li>'
        )
    html = INDEX_TEMPLATE.format(
        count=len(pages),
        entries="\n".join(lines),
    )
    index_path = OUTPUT_ROOT / "index.html"
    index_path.write_text(html, encoding="utf-8")
    return index_path


def collect_existing_pages() -> list[Path]:
    if not OUTPUT_ROOT.is_dir():
        return []
    return sorted(OUTPUT_ROOT.glob("*/*.html"))


def run_batch(folder: Path | None = None) -> int:
    root = (folder or ASSEMBLED_ROOT).expanduser().resolve()
    files = list_assembled_files(root)
    if not files:
        sys.exit(f"No assembled menu files found in {root}")
    ensure_assets()
    print(f"Rendering {len(files)} file(s) from {root}\n")
    pages: list[Path] = []
    failures: list[tuple[str, Exception]] = []
    for p in files:
        try:
            out = render_one(p)
            pages.append(out)
            print(f"  OK   {p.parent.name}/{p.name}")
        except Exception as err:
            failures.append((p.name, err))
            print(f"  FAIL {p.parent.name}/{p.name}: {err}")
    # Always regenerate index using the full set of pages present.
    all_pages = sorted(set(collect_existing_pages()) | set(pages))
    index = write_index(all_pages)
    print()
    if failures:
        print(f"Completed with {len(failures)} failure(s) of {len(files)}.")
    else:
        print(f"Completed: {len(files)} page(s) rendered.")
    print(f"Index:   {index}")
    return 1 if failures else 0


def run_single(source: Path) -> int:
    ensure_assets()
    out = render_one(source)
    pages = sorted(set(collect_existing_pages()) | {out})
    index = write_index(pages)
    print(f"Wrote: {out}")
    print(f"Index: {index}")
    return 0


def interactive() -> int:
    files = list_assembled_files()
    if not files:
        sys.exit(
            f"No assembled menu files found in {ASSEMBLED_ROOT}. "
            "Run assemble_menu.py first."
        )
    width = len(str(len(files)))
    print(f"Assembled menus in {ASSEMBLED_ROOT}:\n")
    for i, p in enumerate(files, 1):
        print(f"  {str(i).rjust(width)}. {p.parent.name}/{p.name}")
    print(f"\n  {'a'.rjust(width)}. [render every assembled menu]")
    print()
    choice = input(
        "Select by number, stem name, or 'a [folder]' for batch: "
    ).strip()
    if not choice:
        sys.exit("No selection made.")
    if choice.lower() == "a" or choice.lower().startswith(("a ", "all ", "batch ")):
        parts = choice.split(None, 1)
        folder = Path(parts[1]).expanduser() if len(parts) > 1 else None
        return run_batch(folder)
    selected = resolve_selection(choice, files)
    if selected is None:
        sys.exit(f"Invalid selection: {choice}")
    return run_single(selected)


def main() -> int:
    args = sys.argv[1:]

    if args and args[0] in {"--batch", "-b", "--all"}:
        folder = Path(args[1]) if len(args) > 1 else None
        return run_batch(folder)

    if len(args) == 1:
        candidate = Path(args[0]).expanduser()
        if candidate.is_dir():
            return run_batch(candidate)
        files = list_assembled_files()
        selected = resolve_selection(args[0], files)
        if selected is None:
            sys.exit(f"Could not resolve: {args[0]}")
        return run_single(selected)

    if args:
        sys.exit(
            "Usage: render_menu.py [<file|stem|index>|<folder>|--batch [folder]]"
        )

    return interactive()


if __name__ == "__main__":
    sys.exit(main())
