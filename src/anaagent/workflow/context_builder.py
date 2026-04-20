"""工作目录环境感知上下文构建。"""

from __future__ import annotations

from pathlib import Path

KEY_FILE_PATTERNS = [
    "README.md",
    "pyproject.toml",
    "package.json",
    "requirements.txt",
    "Makefile",
]

SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".yaml", ".yml", ".json"}


def build_workspace_context(
    workspace_dir: str | Path,
    max_files: int = 80,
    tree_depth: int = 3,
    max_file_excerpt_chars: int = 1200,
) -> dict:
    workspace = Path(workspace_dir).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    tree_lines = _build_tree_lines(workspace, max_files=max_files, max_depth=tree_depth)
    key_files = _collect_key_files(workspace, max_files=12)
    key_file_excerpts = []
    for rel_path in key_files:
        abs_path = workspace / rel_path
        try:
            text = abs_path.read_text(encoding="utf-8")
        except Exception:
            continue
        key_file_excerpts.append(
            {
                "path": str(rel_path),
                "excerpt": text[:max_file_excerpt_chars],
            }
        )

    return {
        "workspace_dir": str(workspace),
        "tree_lines": tree_lines,
        "key_files": [str(p) for p in key_files],
        "key_file_excerpts": key_file_excerpts,
    }


def format_workspace_context(context: dict) -> str:
    tree_text = "\n".join(context.get("tree_lines", [])) or "(empty workspace)"
    file_text = "\n".join(f"- {p}" for p in context.get("key_files", [])) or "- (none)"
    excerpt_blocks = []
    for item in context.get("key_file_excerpts", []):
        excerpt_blocks.append(f"### {item['path']}\n{item['excerpt']}")
    excerpts_text = "\n\n".join(excerpt_blocks) or "(no readable key files)"

    return f"""## Workspace Overview
Path: {context.get("workspace_dir", "")}

### Tree
{tree_text}

### Key Files
{file_text}

### Key File Excerpts
{excerpts_text}
"""


def _build_tree_lines(workspace: Path, max_files: int, max_depth: int) -> list[str]:
    lines = [workspace.name + "/"]
    count = 0
    stack: list[tuple[Path, int]] = [(workspace, 0)]
    while stack and count < max_files:
        current, depth = stack.pop()
        if depth >= max_depth:
            continue
        try:
            entries = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except Exception:
            continue
        for entry in entries:
            if count >= max_files:
                break
            rel = entry.relative_to(workspace)
            prefix = "  " * (depth + 1)
            label = f"{prefix}- {rel.as_posix()}{'/' if entry.is_dir() else ''}"
            lines.append(label)
            count += 1
            if entry.is_dir():
                # 逆序压栈，保证输出稳定
                stack.append((entry, depth + 1))
    return lines


def _collect_key_files(workspace: Path, max_files: int) -> list[Path]:
    files: list[Path] = []
    for pattern in KEY_FILE_PATTERNS:
        matched = workspace / pattern
        if matched.exists() and matched.is_file():
            files.append(matched.relative_to(workspace))

    for p in sorted(workspace.rglob("*")):
        if len(files) >= max_files:
            break
        if not p.is_file():
            continue
        if p.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        rel = p.relative_to(workspace)
        if rel not in files:
            files.append(rel)
    return files[:max_files]
