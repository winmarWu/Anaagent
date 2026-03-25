"""环境管理器 - 核心功能实现"""

import os
import shutil
from pathlib import Path
from typing import Optional

import yaml

from anaagent.models import EnvironmentInfo, OperationResult, TeamConfig

# 默认环境存储路径
ENVS_DIR = Path.home() / ".anaagent" / "environments"
ACTIVE_FILE = Path.home() / ".anaagent" / "active_env"


def _ensure_dirs():
    """确保必要目录存在"""
    ENVS_DIR.mkdir(parents=True, exist_ok=True)
    ENVS_DIR.parent.mkdir(parents=True, exist_ok=True)


def _get_team_path(name: str) -> Path:
    """获取团队环境路径"""
    return ENVS_DIR / name


def _get_active_env() -> Optional[str]:
    """获取当前激活的环境名称"""
    if ACTIVE_FILE.exists():
        return ACTIVE_FILE.read_text(encoding="utf-8").strip()
    return None


def _set_active_env(name: str):
    """设置当前激活的环境"""
    _ensure_dirs()
    ACTIVE_FILE.write_text(name, encoding="utf-8")


def _clear_active_env():
    """清除当前激活的环境"""
    if ACTIVE_FILE.exists():
        ACTIVE_FILE.unlink()


def create_environment(
    name: str,
    description: str = "",
    auth_token: str = "",
    base_url: str = "",
    model: str = ""
) -> OperationResult:
    """
    创建新的团队环境

    设计说明：
    - 参考 conda create -n <name> 的设计
    - 创建完整的目录结构，包括 agents/skills/hooks/commands/mcps/memory
    - 初始化 team.yaml 配置文件（包含Claude配置）
    - 初始化 SQLite 向量数据库
    - 自动创建 main 员工
    """
    _ensure_dirs()
    team_path = _get_team_path(name)

    # 检查是否已存在
    if team_path.exists():
        return OperationResult(
            success=False, message=f"团队 '{name}' 已存在"
        )

    try:
        # 创建目录结构
        dirs = [
            team_path / "agents",
            team_path / "skills",
            team_path / "hooks",
            team_path / "commands",
            team_path / "mcps",
            team_path / "memory" / "memory",
            team_path / ".claude" / "commands",
            team_path / "workspace" / "projects",
            team_path / "workspace" / "shared",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

        # 创建 team.yaml（包含Claude配置）
        config = TeamConfig(
            name=name,
            description=description,
            anthropic_auth_token=auth_token,
            anthropic_base_url=base_url or "https://api.anthropic.com",
            anthropic_model=model or "claude-sonnet-4-6",
        )
        config_path = team_path / "team.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config.model_dump(), f, allow_unicode=True, default_flow_style=False)

        # 创建初始 MEMORY.md
        memory_md = team_path / "memory" / "MEMORY.md"
        memory_md.write_text(f"# Team Memory: {name}\n\n## Important Decisions\n\n## Preferences\n\n## Key Facts\n", encoding="utf-8")

        # 初始化向量数据库
        from anaagent.database import init_database
        init_database(team_path / "memory" / "memory.db")

        # 自动创建 main 员工（直接创建文件，不依赖agent_manager）
        main_agent = {
            "name": "main",
            "role": "assistant",
            "description": f"Default assistant for team {name}",
            "model": model or "claude-sonnet-4-6",
            "anthropic_auth_token": auth_token,
            "anthropic_base_url": base_url,
            "anthropic_model": model,
            "skills": [],
            "system_prompt": "",
            "hooks": {},
            "memory": {"enabled": True, "max_entries": 1000},
            "soul_md": ""
        }
        main_agent_path = team_path / "agents" / "main.yaml"
        with open(main_agent_path, "w", encoding="utf-8") as f:
            yaml.dump(main_agent, f, allow_unicode=True, default_flow_style=False)

        # 同时生成 Claude Code 配置文件
        if auth_token or base_url or model:
            from anaagent.config_manager import generate_claude_config
            generate_claude_config(team_path, auth_token, base_url, model)

        return OperationResult(success=True, path=team_path)

    except Exception as e:
        return OperationResult(success=False, message=str(e))


def list_environments() -> list[EnvironmentInfo]:
    """
    列出所有团队环境

    设计说明：
    - 扫描 ~/.anaagent/environments/ 目录
    - 读取每个团队的 team.yaml 获取元信息
    - 标记当前激活的环境
    """
    _ensure_dirs()
    envs = []
    active_name = _get_active_env()

    for team_dir in ENVS_DIR.iterdir():
        if not team_dir.is_dir():
            continue

        config_path = team_dir / "team.yaml"
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            config = TeamConfig(**data)
        else:
            config = TeamConfig(name=team_dir.name)

        envs.append(
            EnvironmentInfo(
                name=team_dir.name,
                path=team_dir,
                active=(team_dir.name == active_name),
                created_at=config.created_at,
                description=config.description,
            )
        )

    return envs


def activate_environment(name: str) -> OperationResult:
    """
    激活团队环境

    设计说明：
    - 参考 conda activate 的设计
    - 设置 ANAAGENT_ENV 环境变量
    - 记录当前激活状态到 ~/.anaagent/active_env
    - 自动生成 CLAUDE.md 和 Claude Code 集成文件
    - 生成团队上下文文件
    """
    team_path = _get_team_path(name)

    if not team_path.exists():
        return OperationResult(success=False, message=f"Team '{name}' not found")

    _set_active_env(name)
    os.environ["ANAAGENT_ENV"] = str(team_path)

    # 生成 Claude Code 集成文件
    from anaagent.claude_integration import sync_claude_integration
    sync_result = sync_claude_integration()

    # 生成团队上下文文件
    from anaagent.team_context import sync_team_context
    sync_team_context()

    result_msg = str(team_path)
    if sync_result.success:
        result_msg += f"\n  CLAUDE.md generated"

    return OperationResult(success=True, path=team_path, message=result_msg)


def deactivate_environment() -> OperationResult:
    """
    退出当前团队环境

    设计说明：
    - 参考 conda deactivate 的设计
    - 清除激活状态
    - 清除环境变量
    """
    active_name = _get_active_env()
    if not active_name:
        return OperationResult(success=False, message="当前没有激活的团队环境")

    _clear_active_env()
    if "ANAAGENT_ENV" in os.environ:
        del os.environ["ANAAGENT_ENV"]

    return OperationResult(success=True)


def remove_environment(name: str) -> OperationResult:
    """
    删除团队环境

    设计说明：
    - 参考 conda remove -n <name> --all 的设计
    - 完全删除团队目录及所有内容
    - 如果是当前激活的环境，先退出
    """
    team_path = _get_team_path(name)

    if not team_path.exists():
        return OperationResult(success=False, message=f"团队 '{name}' 不存在")

    # 如果是当前激活的环境，先退出
    if _get_active_env() == name:
        deactivate_environment()

    try:
        shutil.rmtree(team_path)
        return OperationResult(success=True)
    except Exception as e:
        return OperationResult(success=False, message=str(e))


def get_current_environment() -> Optional[Path]:
    """获取当前激活的环境路径"""
    active_name = _get_active_env()
    if active_name:
        return _get_team_path(active_name)
    return None