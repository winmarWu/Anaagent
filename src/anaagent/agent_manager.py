"""Agent成员管理模块"""

import shutil
from pathlib import Path
from typing import Optional

import yaml

from anaagent.models import AgentConfig, OperationResult
from anaagent.environment import get_current_environment


def _get_agents_dir() -> Optional[Path]:
    """获取当前团队的agents目录"""
    env_path = get_current_environment()
    if env_path:
        return env_path / "agents"
    return None


def _get_agent_path(name: str) -> Optional[Path]:
    """获取指定agent的配置文件路径"""
    agents_dir = _get_agents_dir()
    if agents_dir:
        return agents_dir / f"{name}.yaml"
    return None


def add_agent(
    name: str,
    role: str = "general",
    description: str = "",
    model: Optional[str] = None,
    skills: Optional[list[str]] = None,
    auth_token: Optional[str] = None,
    base_url: Optional[str] = None,
    anthropic_model: Optional[str] = None,
) -> OperationResult:
    """
    添加Agent成员到当前团队

    设计说明：
    - 参考 OpenClaw Agent 定义格式
    - 创建独立的 yaml 配置文件
    - 支持 role、model、skills 等属性
    - 支持独立的 API 配置（默认继承团队配置）
    """
    agents_dir = _get_agents_dir()
    if not agents_dir:
        return OperationResult(
            success=False, message="No active team environment. Run 'agent activate <name>' first."
        )

    agent_path = agents_dir / f"{name}.yaml"
    if agent_path.exists():
        return OperationResult(success=False, message=f"Agent '{name}' already exists")

    # 创建Agent配置
    config = AgentConfig(
        name=name,
        role=role,
        description=description,
        model=model,
        skills=skills or [],
        anthropic_auth_token=auth_token,
        anthropic_base_url=base_url,
        anthropic_model=anthropic_model,
    )

    try:
        with open(agent_path, "w", encoding="utf-8") as f:
            yaml.dump(config.model_dump(), f, allow_unicode=True, default_flow_style=False)
        return OperationResult(success=True, path=agent_path)
    except Exception as e:
        return OperationResult(success=False, message=str(e))


def remove_agent(name: str) -> OperationResult:
    """移除Agent成员"""
    agent_path = _get_agent_path(name)
    if not agent_path:
        return OperationResult(success=False, message="No active team environment")

    if not agent_path.exists():
        return OperationResult(success=False, message=f"Agent '{name}' not found")

    try:
        agent_path.unlink()
        return OperationResult(success=True)
    except Exception as e:
        return OperationResult(success=False, message=str(e))


def list_agents() -> list[AgentConfig]:
    """列出当前团队所有Agent成员"""
    agents_dir = _get_agents_dir()
    if not agents_dir or not agents_dir.exists():
        return []

    agents = []
    for agent_file in agents_dir.glob("*.yaml"):
        try:
            with open(agent_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            agents.append(AgentConfig(**data))
        except Exception:
            continue

    return agents


def get_agent(name: str) -> Optional[AgentConfig]:
    """获取指定Agent的配置"""
    agent_path = _get_agent_path(name)
    if not agent_path or not agent_path.exists():
        return None

    try:
        with open(agent_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return AgentConfig(**data)
    except Exception:
        return None


def update_agent(name: str, **kwargs) -> OperationResult:
    """更新Agent配置"""
    agent_path = _get_agent_path(name)
    if not agent_path:
        return OperationResult(success=False, message="No active team environment")

    if not agent_path.exists():
        return OperationResult(success=False, message=f"Agent '{name}' not found")

    try:
        with open(agent_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # 更新指定字段
        for key, value in kwargs.items():
            if value is not None:
                data[key] = value

        with open(agent_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

        return OperationResult(success=True, path=agent_path)
    except Exception as e:
        return OperationResult(success=False, message=str(e))