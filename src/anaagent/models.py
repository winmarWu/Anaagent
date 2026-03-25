"""数据模型 - 使用Pydantic定义"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class OperationResult(BaseModel):
    """操作结果通用模型"""

    success: bool
    message: str = ""
    path: Optional[Path] = None


class TeamConfig(BaseModel):
    """团队配置模型 (team.yaml)"""

    name: str
    description: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    activated: bool = False
    default_model: str = "claude-sonnet-4-6"
    # Claude API 配置
    anthropic_auth_token: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_model: str = "claude-sonnet-4-6"
    api_keys: dict = Field(default_factory=dict)
    settings: dict = Field(
        default_factory=lambda: {
            "max_tokens_per_day": 100000,
            "memory_compression": True,
            "hooks_enabled": True,
        }
    )


class AgentConfig(BaseModel):
    """Agent成员配置模型"""

    name: str
    role: str = "general"
    description: str = ""
    model: Optional[str] = None  # 覆盖团队默认模型
    # Claude API 配置
    anthropic_auth_token: Optional[str] = None
    anthropic_base_url: Optional[str] = None
    anthropic_model: Optional[str] = None
    skills: list[str] = Field(default_factory=list)
    system_prompt: str = ""
    hooks: dict = Field(default_factory=dict)
    memory: dict = Field(default_factory=lambda: {"enabled": True, "max_entries": 1000})
    soul_md: str = ""


class EnvironmentInfo(BaseModel):
    """环境信息模型（用于列表显示）"""

    name: str
    path: Path
    active: bool = False
    created_at: str = ""
    description: str = ""


class SkillMetadata(BaseModel):
    """技能包元数据"""

    name: str
    description: str = ""
    version: str = "1.0.0"
    author: str = "community"
    dependencies: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)