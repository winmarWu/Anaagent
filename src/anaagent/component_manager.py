"""组件管理模块 - Skills, MCPs, Hooks的安装和管理"""

import json
import shutil
from pathlib import Path
from typing import Optional

import yaml

from anaagent.models import OperationResult, SkillMetadata
from anaagent.environment import get_current_environment


def _get_component_dir(component_type: str) -> Optional[Path]:
    """获取指定类型组件的目录"""
    env_path = get_current_environment()
    if not env_path:
        return None

    dirs = {
        "skill": env_path / "skills",
        "mcp": env_path / "mcps",
        "hook": env_path / "hooks",
    }
    return dirs.get(component_type)


# ============================================
# Skill 管理
# ============================================

def install_skill(name: str, source: Optional[str] = None) -> OperationResult:
    """
    安装技能包

    设计说明：
    - 参考 pip install 的设计
    - 支持从本地路径或市场安装
    - 创建 SKILL.md 文件
    """
    skills_dir = _get_component_dir("skill")
    if not skills_dir:
        return OperationResult(
            success=False, message="No active team environment. Run 'anaagent env activate <name>' first."
        )

    skill_path = skills_dir / name

    # 如果提供了源路径，从源复制
    if source:
        source_path = Path(source)
        if source_path.exists():
            try:
                if skill_path.exists():
                    shutil.rmtree(skill_path)
                shutil.copytree(source_path, skill_path)
                return OperationResult(success=True, path=skill_path)
            except Exception as e:
                return OperationResult(success=False, message=str(e))
        else:
            return OperationResult(success=False, message=f"Source path not found: {source}")

    # 否则创建默认技能模板
    if skill_path.exists():
        return OperationResult(success=False, message=f"Skill '{name}' already exists")

    try:
        skill_path.mkdir(parents=True, exist_ok=True)
        skill_md = skill_path / "SKILL.md"

        # 默认技能模板
        template = f'''---
name: {name}
description: Skill for {name}
version: 1.0.0
author: local
dependencies: []
triggers:
  - {name.lower()}
---

# {name} Skill

## Role Definition
Define the agent's role and expertise here.

## Execution Steps
1. Step 1
2. Step 2
3. Step 3

## Output Standards
Define expected output format and quality standards.
'''
        skill_md.write_text(template, encoding="utf-8")
        return OperationResult(success=True, path=skill_path)

    except Exception as e:
        return OperationResult(success=False, message=str(e))


def list_skills() -> list[dict]:
    """列出已安装的技能"""
    skills_dir = _get_component_dir("skill")
    if not skills_dir or not skills_dir.exists():
        return []

    skills = []
    for skill_dir in skills_dir.iterdir():
        if not skill_dir.is_dir():
            continue

        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            # 解析 YAML frontmatter
            metadata = _parse_skill_metadata(skill_md)
            skills.append({
                "name": skill_dir.name,
                "path": str(skill_dir),
                **metadata
            })

    return skills


def _parse_skill_metadata(skill_md: Path) -> dict:
    """解析 SKILL.md 的 YAML frontmatter"""
    try:
        content = skill_md.read_text(encoding="utf-8")
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                metadata = yaml.safe_load(parts[1])
                return metadata or {}
    except Exception:
        pass
    return {}


def remove_skill(name: str) -> OperationResult:
    """移除技能包"""
    skills_dir = _get_component_dir("skill")
    if not skills_dir:
        return OperationResult(success=False, message="No active team environment")

    skill_path = skills_dir / name
    if not skill_path.exists():
        return OperationResult(success=False, message=f"Skill '{name}' not found")

    try:
        shutil.rmtree(skill_path)
        return OperationResult(success=True)
    except Exception as e:
        return OperationResult(success=False, message=str(e))


# ============================================
# MCP 管理
# ============================================

def install_mcp(name: str, config: Optional[str] = None) -> OperationResult:
    """
    安装 MCP 服务配置

    设计说明：
    - MCP (Model Context Protocol) 服务配置
    - 支持 JSON 格式的配置参数
    """
    mcps_dir = _get_component_dir("mcp")
    if not mcps_dir:
        return OperationResult(
            success=False, message="No active team environment. Run 'anaagent env activate <name>' first."
        )

    mcp_path = mcps_dir / f"{name}.yaml"

    try:
        # 解析配置
        config_data = {}
        if config:
            try:
                config_data = json.loads(config)
            except json.JSONDecodeError:
                config_data = {"raw_config": config}

        # 创建 MCP 配置
        mcp_config = {
            "name": name,
            "enabled": True,
            "config": config_data
        }

        mcps_dir.mkdir(parents=True, exist_ok=True)
        with open(mcp_path, "w", encoding="utf-8") as f:
            yaml.dump(mcp_config, f, allow_unicode=True, default_flow_style=False)

        return OperationResult(success=True, path=mcp_path)

    except Exception as e:
        return OperationResult(success=False, message=str(e))


def list_mcps() -> list[dict]:
    """列出已安装的 MCP 服务"""
    mcps_dir = _get_component_dir("mcp")
    if not mcps_dir or not mcps_dir.exists():
        return []

    mcps = []
    for mcp_file in mcps_dir.glob("*.yaml"):
        try:
            with open(mcp_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            mcps.append({
                "name": mcp_file.stem,
                "path": str(mcp_file),
                "status": "enabled" if data.get("enabled") else "disabled"
            })
        except Exception:
            continue

    return mcps


def remove_mcp(name: str) -> OperationResult:
    """移除 MCP 服务"""
    mcps_dir = _get_component_dir("mcp")
    if not mcps_dir:
        return OperationResult(success=False, message="No active team environment")

    mcp_path = mcps_dir / f"{name}.yaml"
    if not mcp_path.exists():
        return OperationResult(success=False, message=f"MCP '{name}' not found")

    try:
        mcp_path.unlink()
        return OperationResult(success=True)
    except Exception as e:
        return OperationResult(success=False, message=str(e))


# ============================================
# Hook 管理
# ============================================

def install_hook(name: str, source: Optional[str] = None) -> OperationResult:
    """
    安装 Hook 脚本

    设计说明：
    - 参考 Claude Code Hooks 系统
    - 支持多种 Hook 类型
    """
    hooks_dir = _get_component_dir("hook")
    if not hooks_dir:
        return OperationResult(
            success=False, message="No active team environment. Run 'anaagent env activate <name>' first."
        )

    hook_path = hooks_dir / name

    # 如果提供了源路径，从源复制
    if source:
        source_path = Path(source)
        if source_path.exists():
            try:
                shutil.copy2(source_path, hook_path)
                return OperationResult(success=True, path=hook_path)
            except Exception as e:
                return OperationResult(success=False, message=str(e))
        else:
            return OperationResult(success=False, message=f"Source path not found: {source}")

    # 创建默认 Hook 模板
    if hook_path.exists():
        return OperationResult(success=False, message=f"Hook '{name}' already exists")

    try:
        hooks_dir.mkdir(parents=True, exist_ok=True)

        # 根据 extension 确定 hook 类型
        if name.endswith(".py"):
            template = f'''"""
Hook: {name}
Type: PreToolUse / PostToolUse / etc.

Claude Code Hooks:
- PreToolUse: Before tool call (can block)
- PostToolUse: After tool call
- UserPromptSubmit: After user input
- SessionStart: Session start
- SessionEnd: Session end
"""

import sys
import json

def main():
    # Read hook input from stdin
    input_data = json.load(sys.stdin)

    # Your hook logic here
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {{}})

    # Example: Block certain operations
    # if tool_name == "Bash" and "rm -rf" in tool_input.get("command", ""):
    #     print(json.dumps({{"block": True, "reason": "Dangerous command"}}))
    #     return

    # Pass through
    print(json.dumps({{"block": False}}))

if __name__ == "__main__":
    main()
'''
        else:
            template = f'''#!/bin/bash
# Hook: {name}
# Type: PreToolUse / PostToolUse / etc.

# Read input from stdin
read -r input

# Your hook logic here
# echo "$input" | jq '.'

# Output: {{"block": false}} to allow, {{"block": true, "reason": "..."}} to block
echo '{{"block": false}}'
'''

        hook_path.write_text(template, encoding="utf-8")
        return OperationResult(success=True, path=hook_path)

    except Exception as e:
        return OperationResult(success=False, message=str(e))


def list_hooks() -> list[dict]:
    """列出已安装的 Hooks"""
    hooks_dir = _get_component_dir("hook")
    if not hooks_dir or not hooks_dir.exists():
        return []

    hooks = []
    for hook_file in hooks_dir.iterdir():
        if hook_file.is_file():
            # 根据扩展名确定类型
            ext = hook_file.suffix.lower()
            hook_type = {
                ".py": "Python",
                ".sh": "Shell",
                ".js": "JavaScript",
            }.get(ext, ext or "Unknown")

            hooks.append({
                "name": hook_file.name,
                "path": str(hook_file),
                "type": hook_type
            })

    return hooks


def remove_hook(name: str) -> OperationResult:
    """移除 Hook"""
    hooks_dir = _get_component_dir("hook")
    if not hooks_dir:
        return OperationResult(success=False, message="No active team environment")

    hook_path = hooks_dir / name
    if not hook_path.exists():
        return OperationResult(success=False, message=f"Hook '{name}' not found")

    try:
        hook_path.unlink()
        return OperationResult(success=True)
    except Exception as e:
        return OperationResult(success=False, message=str(e))