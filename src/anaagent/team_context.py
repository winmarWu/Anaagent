"""团队上下文生成器 - 生成CLAUDE.md让Claude了解当前团队"""

from pathlib import Path
from typing import Optional

import yaml


def generate_team_context(team_path: Path) -> str:
    """
    生成团队上下文文件内容

    包括：
    - 团队基本信息
    - Agent成员列表
    - 可用Skills
    - 可用MCP服务
    - 可用Hooks
    - Memory摘要
    - 工作目录说明
    """
    team_yaml_path = team_path / "team.yaml"

    # 读取团队配置
    config = {}
    if team_yaml_path.exists():
        with open(team_yaml_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    team_name = config.get("name", team_path.name)
    description = config.get("description", "")
    model = config.get("anthropic_model", "claude-sonnet-4-6")

    # 统计成员及其详细信息
    agents_dir = team_path / "agents"
    agents = []
    if agents_dir.exists():
        for agent_file in agents_dir.glob("*.yaml"):
            try:
                with open(agent_file, encoding="utf-8") as f:
                    agent_config = yaml.safe_load(f) or {}

                agent_name = agent_config.get("name", agent_file.stem)
                agent_info = {
                    "name": agent_name,
                    "role": agent_config.get("role", "member"),
                    "skills": agent_config.get("skills", []),
                    "mcps": agent_config.get("mcps", []),
                    "soul_md": "",
                    "memory": "",
                }

                # 读取 soul.md
                soul_path = agents_dir / agent_name / "soul.md"
                if soul_path.exists():
                    try:
                        agent_info["soul_md"] = soul_path.read_text(encoding="utf-8")[:1000]
                    except Exception:
                        pass

                # 读取 agent memory
                memory_path = agents_dir / agent_name / "memory" / "MEMORY.md"
                if memory_path.exists():
                    try:
                        agent_info["memory"] = memory_path.read_text(encoding="utf-8")[:500]
                    except Exception:
                        pass

                agents.append(agent_info)
            except Exception:
                pass

    # 统计Skills
    skills_dir = team_path / "skills"
    skills = []
    if skills_dir.exists():
        for skill_dir in skills_dir.iterdir():
            if skill_dir.is_dir():
                skill_md = skill_dir / "SKILL.md"
                if skill_md.exists():
                    skills.append(skill_dir.name)

    # 统计MCPs
    mcps_dir = team_path / "mcps"
    mcps = []
    if mcps_dir.exists():
        for mcp_dir in mcps_dir.iterdir():
            if mcp_dir.is_dir():
                mcps.append(mcp_dir.name)

    # 统计Hooks
    hooks_dir = team_path / "hooks"
    hooks = []
    if hooks_dir.exists():
        for hook_file in hooks_dir.glob("*.py"):
            hooks.append(hook_file.stem)

    # 读取Memory摘要
    memory_path = team_path / "memory" / "MEMORY.md"
    memory_content = ""
    if memory_path.exists():
        try:
            memory_content = memory_path.read_text(encoding="utf-8")[:2000]  # 限制长度
        except Exception:
            pass

    # 生成上下文
    context = f"""# Anaagent Team Context

## Current Mode
You are working in **Anaagent Team Mode**. This is a virtual team environment where you can collaborate with other AI agents and use team resources.

---

## Team: {team_name}

**Description:** {description or "No description"}

**Default Model:** {model}

**Working Directory:** `{team_path}/workspace/projects/`

---

## Team Members ({len(agents)})

"""

    if agents:
        for agent in agents:
            skills_str = ", ".join(agent["skills"]) if agent["skills"] else "-"
            mcps_str = ", ".join(agent["mcps"]) if agent["mcps"] else "-"
            context += f"### {agent['name']}\n"
            context += f"- **Role:** {agent['role']}\n"
            context += f"- **Skills:** {skills_str}\n"
            context += f"- **MCPs:** {mcps_str}\n"

            # 添加 soul.md 内容
            if agent["soul_md"]:
                context += f"\n**Soul (性格/角色定义):**\n```\n{agent['soul_md']}\n```\n"

            # 添加 memory 内容
            if agent["memory"]:
                context += f"\n**Memory (记忆):**\n```\n{agent['memory']}\n```\n"

            context += "\n"
    else:
        context += "No team members configured yet.\n\n"

    context += f"""---

## Available Skills ({len(skills)})

"""

    if skills:
        for skill in skills:
            context += f"- `{skill}`\n"
    else:
        context += "No skills installed. Use `agent market install skill <name>` to install.\n"

    context += f"""
---

## Available MCP Services ({len(mcps)})

"""

    if mcps:
        for mcp in mcps:
            context += f"- `{mcp}`\n"
    else:
        context += "No MCP services configured. Use `agent market install mcp <name>` to install.\n"

    context += f"""
---

## Available Hooks ({len(hooks)})

"""

    if hooks:
        for hook in hooks:
            context += f"- `{hook}`\n"
    else:
        context += "No hooks configured. Use `agent market install hook <name>` to install.\n"

    if memory_content:
        context += f"""
---

## Team Memory

{memory_content}
"""

    context += f"""
---

## Quick Commands

```bash
# Team management
agent list                    # List all teams
agent info                    # Show current team info
agent member list             # List team members

# Configuration
agent config show-team        # Show team configuration

# Market
agent market list             # List available skills/MCPs
agent market install skill <name>   # Install a skill
agent market install mcp <name>     # Install an MCP

# Memory
agent memory add "content"    # Add to team memory
agent memory recall "query"   # Search memory
```

---

## Important Notes

1. You are in **{team_name}** team environment
2. Your working directory should be `{team_path}/workspace/projects/`
3. All team members share the same memory and resources
4. Use `agent` commands to manage the team

*Generated by Anaagent*
"""

    return context


def sync_team_context() -> bool:
    """同步团队上下文文件"""
    from anaagent.environment import get_current_environment

    team_path = get_current_environment()
    if not team_path:
        return False

    try:
        # 生成上下文
        context = generate_team_context(team_path)

        # 写入CLAUDE.md到团队根目录
        claude_md_path = team_path / "CLAUDE.md"
        claude_md_path.write_text(context, encoding="utf-8")

        # 也写入到workspace/projects目录
        projects_dir = team_path / "workspace" / "projects"
        projects_dir.mkdir(parents=True, exist_ok=True)
        workspace_claude_md = projects_dir / "CLAUDE.md"
        workspace_claude_md.write_text(context, encoding="utf-8")

        return True
    except Exception as e:
        print(f"Error syncing team context: {e}")
        return False