"""Commands 命令系统 - 参考 Claude Code Commands 设计"""

import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import yaml

from anaagent.environment import get_current_environment


@dataclass
class CommandDefinition:
    """命令定义"""
    name: str
    description: str
    argument_hint: str = ""
    allowed_tools: list = None
    model: Optional[str] = None
    content: str = ""

    def __post_init__(self):
        if self.allowed_tools is None:
            self.allowed_tools = []


def get_commands_dir() -> Optional[Path]:
    """获取commands目录"""
    env_path = get_current_environment()
    if env_path:
        return env_path / "commands"
    return None


def get_claude_commands_dir() -> Optional[Path]:
    """获取.claude/commands目录"""
    env_path = get_current_environment()
    if env_path:
        return env_path / ".claude" / "commands"
    return None


def parse_command_file(file_path: Path) -> Optional[CommandDefinition]:
    """
    解析命令文件

    格式：Markdown文件，开头是YAML frontmatter
    """
    if not file_path.exists():
        return None

    try:
        content = file_path.read_text(encoding="utf-8")

        # 解析YAML frontmatter
        metadata = {}
        body = content

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                metadata = yaml.safe_load(parts[1]) or {}
                body = parts[2].strip()

        return CommandDefinition(
            name=file_path.stem,
            description=metadata.get("description", ""),
            argument_hint=metadata.get("argument-hint", ""),
            allowed_tools=metadata.get("allowed-tools", []),
            model=metadata.get("model"),
            content=body
        )

    except Exception as e:
        print(f"Error parsing command file {file_path}: {e}")
        return None


def list_commands() -> list[CommandDefinition]:
    """列出所有可用命令"""
    commands = []

    # 团队级命令
    commands_dir = get_commands_dir()
    if commands_dir and commands_dir.exists():
        for cmd_file in commands_dir.glob("*.md"):
            cmd = parse_command_file(cmd_file)
            if cmd:
                cmd.name = cmd_file.stem
                commands.append(cmd)

    # .claude/commands 目录的命令
    claude_commands_dir = get_claude_commands_dir()
    if claude_commands_dir and claude_commands_dir.exists():
        for cmd_file in claude_commands_dir.glob("*.md"):
            cmd = parse_command_file(cmd_file)
            if cmd:
                cmd.name = cmd_file.stem
                commands.append(cmd)

    return commands


def get_command(name: str) -> Optional[CommandDefinition]:
    """获取指定命令"""
    # 先查找团队级命令
    commands_dir = get_commands_dir()
    if commands_dir:
        cmd_file = commands_dir / f"{name}.md"
        if cmd_file.exists():
            return parse_command_file(cmd_file)

    # 再查找.claude/commands
    claude_commands_dir = get_claude_commands_dir()
    if claude_commands_dir:
        cmd_file = claude_commands_dir / f"{name}.md"
        if cmd_file.exists():
            return parse_command_file(cmd_file)

    return None


def create_command(
    name: str,
    description: str = "",
    content: str = "",
    argument_hint: str = "",
    allowed_tools: list = None,
    model: str = None
) -> Path:
    """
    创建新命令

    Args:
        name: 命令名称
        description: 命令描述
        content: 命令内容(提示词)
        argument_hint: 参数提示
        allowed_tools: 允许的工具列表
        model: 指定模型

    Returns:
        创建的文件路径
    """
    commands_dir = get_commands_dir()
    if not commands_dir:
        raise RuntimeError("No active team environment")

    commands_dir.mkdir(parents=True, exist_ok=True)

    # 构建YAML frontmatter
    frontmatter = {
        "description": description,
    }
    if argument_hint:
        frontmatter["argument-hint"] = argument_hint
    if allowed_tools:
        frontmatter["allowed-tools"] = allowed_tools
    if model:
        frontmatter["model"] = model

    # 生成文件内容
    yaml_str = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False)
    file_content = f"---\n{yaml_str}---\n\n{content}"

    # 写入文件
    cmd_path = commands_dir / f"{name}.md"
    cmd_path.write_text(file_content, encoding="utf-8")

    return cmd_path


def render_command_prompt(command: CommandDefinition, arguments: str = "") -> str:
    """
    渲染命令提示词

    Args:
        command: 命令定义
        arguments: 用户传入的参数

    Returns:
        渲染后的提示词
    """
    prompt = command.content

    # 替换 $ARGUMENTS 变量
    prompt = prompt.replace("$ARGUMENTS", arguments)

    return prompt