"""Claude Code 集成模块 - 生成CLAUDE.md、Hooks执行等"""

from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from anaagent.environment import get_current_environment
from anaagent.models import OperationResult


def get_claude_md_path() -> Optional[Path]:
    """获取CLAUDE.md文件路径"""
    env_path = get_current_environment()
    if env_path:
        return env_path / "CLAUDE.md"
    return None


def get_claude_dir() -> Optional[Path]:
    """获取.claude目录路径"""
    env_path = get_current_environment()
    if env_path:
        return env_path / ".claude"
    return None


def generate_claude_md() -> OperationResult:
    """
    生成 CLAUDE.md 文件

    设计说明：
    - 参考 PRD 3.8 Claude Code集成
    - 激活团队时自动生成
    - 注入团队上下文：成员、技能、记忆要点
    """
    env_path = get_current_environment()
    if not env_path:
        return OperationResult(success=False, message="No active team environment")

    # 加载团队配置
    team_yaml = env_path / "team.yaml"
    if not team_yaml.exists():
        return OperationResult(success=False, message="team.yaml not found")

    with open(team_yaml, encoding="utf-8") as f:
        team = yaml.safe_load(f)

    # 加载Agent成员
    agents = []
    agents_dir = env_path / "agents"
    if agents_dir.exists():
        for agent_file in agents_dir.glob("*.yaml"):
            with open(agent_file, encoding="utf-8") as f:
                agents.append(yaml.safe_load(f))

    # 加载已安装技能
    skills = []
    skills_dir = env_path / "skills"
    if skills_dir.exists():
        for skill_dir in skills_dir.iterdir():
            if skill_dir.is_dir():
                skill_md = skill_dir / "SKILL.md"
                if skill_md.exists():
                    # 解析元数据
                    content = skill_md.read_text(encoding="utf-8")
                    if content.startswith("---"):
                        parts = content.split("---", 2)
                        if len(parts) >= 3:
                            metadata = yaml.safe_load(parts[1])
                            skills.append({
                                "name": skill_dir.name,
                                "description": metadata.get("description", "") if metadata else ""
                            })

    # 加载记忆要点
    memory_highlights = []
    memory_md = env_path / "memory" / "MEMORY.md"
    if memory_md.exists():
        content = memory_md.read_text(encoding="utf-8")
        # 提取重要决策和偏好设置部分
        lines = content.split("\n")
        in_section = False
        for line in lines:
            if line.startswith("## "):
                in_section = "决策" in line or "偏好" in line or "重要" in line
            elif in_section and line.strip().startswith("- "):
                memory_highlights.append(line.strip()[2:])

    # 生成CLAUDE.md内容
    content = _render_claude_md(team, agents, skills, memory_highlights)

    # 写入文件
    claude_md_path = env_path / "CLAUDE.md"
    claude_md_path.write_text(content, encoding="utf-8")

    return OperationResult(success=True, path=claude_md_path)


def _render_claude_md(team: dict, agents: list, skills: list, memory: list) -> str:
    """渲染CLAUDE.md内容"""

    # 团队信息
    lines = [
        f"# Team: {team.get('name', 'Unknown')}",
        "",
        "## Team Overview",
        team.get("description", "No description"),
        "",
        "## Default Model",
        f"`{team.get('default_model', 'claude-sonnet-4-6')}`",
        "",
    ]

    # 团队成员
    if agents:
        lines.append("## Team Members")
        lines.append("")
        for agent in agents:
            model = agent.get("model") or "(use default)"
            role = agent.get("role", "general")
            desc = agent.get("description", "")
            agent_skills = agent.get("skills", [])

            lines.append(f"### {agent.get('name', 'Unknown')}")
            lines.append(f"- **Role**: {role}")
            lines.append(f"- **Model**: {model}")
            if desc:
                lines.append(f"- **Description**: {desc}")
            if agent_skills:
                lines.append(f"- **Skills**: {', '.join(agent_skills)}")
            lines.append("")

    # 已安装技能
    if skills:
        lines.append("## Installed Skills")
        lines.append("")
        for skill in skills:
            lines.append(f"- **{skill['name']}**: {skill.get('description', '')}")
        lines.append("")

    # 记忆要点
    if memory:
        lines.append("## Memory Highlights")
        lines.append("")
        for item in memory[:10]:  # 最多显示10条
            lines.append(f"- {item}")
        lines.append("")

    # 工作规范
    lines.extend([
        "## Work Guidelines",
        "",
        "### When working in this team:",
        "1. Follow the team's coding standards and conventions",
        "2. Use the installed skills when relevant tasks arise",
        "3. Consider consulting appropriate team members for their expertise",
        "4. Document important decisions in memory",
        "",
        "### Team Settings:",
    ])

    settings = team.get("settings", {})
    for key, value in settings.items():
        lines.append(f"- {key}: {value}")

    lines.append("")
    lines.append("---")
    lines.append(f"Generated by Anaagent at {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    return "\n".join(lines)


def generate_settings_json() -> OperationResult:
    """
    生成 .claude/settings.json

    设计说明：
    - 配置Hooks执行规则
    - 权限设置
    """
    env_path = get_current_environment()
    if not env_path:
        return OperationResult(success=False, message="No active team environment")

    claude_dir = env_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)

    settings_path = claude_dir / "settings.json"

    # 收集已安装的hooks
    hooks_config = _collect_hooks_config(env_path)

    # 基础settings
    settings = {
        "hooks": hooks_config,
        "permissions": {
            "allow": [
                "Read(**)",
                "Glob(**)",
                "Grep(**)",
            ],
            "deny": []
        }
    }

    import json
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)

    return OperationResult(success=True, path=settings_path)


def _collect_hooks_config(env_path: Path) -> dict:
    """收集Hooks配置"""
    hooks_dir = env_path / "hooks"
    if not hooks_dir.exists():
        return {}

    # 读取team.yaml中的hooks配置
    team_yaml = env_path / "team.yaml"
    if team_yaml.exists():
        with open(team_yaml, encoding="utf-8") as f:
            team = yaml.safe_load(f)
        if team.get("settings", {}).get("hooks_enabled"):
            # 返回默认的hooks配置
            return {
                "PostToolUse": [
                    {
                        "matcher": "Write|Edit",
                        "hooks": []
                    }
                ]
            }

    return {}


def sync_claude_integration() -> OperationResult:
    """
    同步Claude Code集成

    在激活环境后调用，生成所有必要文件
    """
    result1 = generate_claude_md()
    result2 = generate_settings_json()

    if result1.success and result2.success:
        return OperationResult(
            success=True,
            message=f"CLAUDE.md: {result1.path}\nsettings.json: {result2.path}"
        )
    else:
        messages = []
        if not result1.success:
            messages.append(f"CLAUDE.md: {result1.message}")
        if not result2.success:
            messages.append(f"settings.json: {result2.message}")
        return OperationResult(success=False, message="; ".join(messages))