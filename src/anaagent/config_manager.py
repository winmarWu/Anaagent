"""配置管理模块 - API Key、团队设置等"""

import json
from pathlib import Path
from typing import Optional

import yaml

from anaagent.models import OperationResult
from anaagent.environment import get_current_environment

# Base环境配置文件路径
BASE_CONFIG_FILE = Path.home() / ".anaagent" / "base_config.json"


def get_base_config() -> dict:
    """获取base环境的默认配置"""
    if BASE_CONFIG_FILE.exists():
        try:
            with open(BASE_CONFIG_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "anthropic_auth_token": "",
        "anthropic_base_url": "https://api.anthropic.com",
        "anthropic_model": "claude-sonnet-4-6"
    }


def set_base_config(auth_token: str = None, base_url: str = None, model: str = None) -> OperationResult:
    """设置base环境的默认配置"""
    config = get_base_config()

    if auth_token is not None:
        config["anthropic_auth_token"] = auth_token
    if base_url is not None:
        config["anthropic_base_url"] = base_url
    if model is not None:
        config["anthropic_model"] = model

    try:
        BASE_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(BASE_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        return OperationResult(success=True)
    except Exception as e:
        return OperationResult(success=False, message=str(e))


def mask_token(token: str) -> str:
    """掩码显示token"""
    if not token:
        return "(not set)"
    if len(token) > 8:
        return f"{token[:4]}...{token[-4:]}"
    return "***"


def get_config_path() -> Optional[Path]:
    """获取当前团队的配置文件路径"""
    env_path = get_current_environment()
    if env_path:
        return env_path / "team.yaml"
    return None


def load_config() -> Optional[dict]:
    """加载团队配置"""
    config_path = get_config_path()
    if not config_path or not config_path.exists():
        return None

    try:
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def save_config(config: dict) -> OperationResult:
    """保存团队配置"""
    config_path = get_config_path()
    if not config_path:
        return OperationResult(success=False, message="No active team environment")

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        return OperationResult(success=True)
    except Exception as e:
        return OperationResult(success=False, message=str(e))


# ============================================
# Claude Code 配置生成
# ============================================

def generate_claude_config(team_path: Path, auth_token: str, base_url: str, model: str) -> OperationResult:
    """生成Claude Code所需的配置文件"""
    try:
        claude_dir = team_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)

        # 生成 settings.json (Claude Code环境变量配置)
        settings = {
            "env": {
                "ANTHROPIC_AUTH_TOKEN": auth_token,
                "ANTHROPIC_BASE_URL": base_url,
                "ANTHROPIC_MODEL": model
            }
        }
        settings_path = claude_dir / "settings.json"
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)

        # 生成 .claude.json (完成onboarding标记)
        claude_json = {"hasCompletedOnboarding": True}
        claude_json_path = team_path / ".claude.json"
        with open(claude_json_path, "w", encoding="utf-8") as f:
            json.dump(claude_json, f, indent=2)

        # 同时更新 team.yaml
        team_yaml_path = team_path / "team.yaml"
        if team_yaml_path.exists():
            with open(team_yaml_path, encoding="utf-8") as f:
                team_config = yaml.safe_load(f) or {}
            team_config["anthropic_auth_token"] = auth_token
            team_config["anthropic_base_url"] = base_url
            team_config["anthropic_model"] = model
            with open(team_yaml_path, "w", encoding="utf-8") as f:
                yaml.dump(team_config, f, allow_unicode=True, default_flow_style=False)

        return OperationResult(success=True)
    except Exception as e:
        return OperationResult(success=False, message=str(e))


def update_team_claude_config(auth_token: str = None, base_url: str = None, model: str = None) -> OperationResult:
    """更新当前团队的Claude配置（同时更新team.yaml和.claude/settings.json，并刷新CLAUDE.md）"""
    from anaagent.environment import get_current_environment
    from anaagent.team_context import sync_team_context

    env_path = get_current_environment()
    if not env_path:
        return OperationResult(success=False, message="No active team environment")

    team_yaml_path = env_path / "team.yaml"

    # 读取现有配置
    if team_yaml_path.exists():
        with open(team_yaml_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}

    # 更新配置
    if auth_token is not None:
        config["anthropic_auth_token"] = auth_token
    if base_url is not None:
        config["anthropic_base_url"] = base_url
    if model is not None:
        config["anthropic_model"] = model

    # 保存到team.yaml
    with open(team_yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

    # 同时更新.claude/settings.json
    final_token = config.get("anthropic_auth_token", "")
    final_url = config.get("anthropic_base_url", "https://api.anthropic.com")
    final_model = config.get("anthropic_model", "claude-sonnet-4-6")

    result = generate_claude_config(env_path, final_token, final_url, final_model)
    if not result.success:
        return result

    # 重新生成CLAUDE.md（包含最新的团队配置信息）
    sync_team_context()

    return OperationResult(success=True)


# ============================================
# API Key 管理
# ============================================

def set_api_key(provider: str, key: str) -> OperationResult:
    """
    设置 API Key

    Args:
        provider: 提供商名称 (如 anthropic, openai)
        key: API密钥
    """
    config = load_config()
    if not config:
        return OperationResult(success=False, message="No active team environment")

    if "api_keys" not in config:
        config["api_keys"] = {}

    # 存储时只显示前后几位
    config["api_keys"][provider] = key

    return save_config(config)


def get_api_key(provider: str) -> Optional[str]:
    """获取指定提供商的 API Key"""
    config = load_config()
    if not config or "api_keys" not in config:
        return None
    return config["api_keys"].get(provider)


def list_api_keys() -> dict:
    """列出所有 API Keys (掩码显示)"""
    config = load_config()
    if not config or "api_keys" not in config:
        return {}

    # 返回掩码后的 keys
    masked = {}
    for provider, key in config["api_keys"].items():
        if key:
            # 只显示前4位和后4位
            masked[provider] = f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "***"
        else:
            masked[provider] = "(not set)"

    return masked


def remove_api_key(provider: str) -> OperationResult:
    """移除 API Key"""
    config = load_config()
    if not config:
        return OperationResult(success=False, message="No active team environment")

    if "api_keys" not in config or provider not in config["api_keys"]:
        return OperationResult(success=False, message=f"API key for '{provider}' not found")

    del config["api_keys"][provider]
    return save_config(config)


# ============================================
# 团队设置管理
# ============================================

def get_setting(key: str) -> Optional[str]:
    """获取团队设置项"""
    config = load_config()
    if not config or "settings" not in config:
        return None
    return config["settings"].get(key)


def set_setting(key: str, value: str) -> OperationResult:
    """设置团队配置项"""
    config = load_config()
    if not config:
        return OperationResult(success=False, message="No active team environment")

    if "settings" not in config:
        config["settings"] = {}

    config["settings"][key] = value
    return save_config(config)


def get_all_settings() -> dict:
    """获取所有设置"""
    config = load_config()
    if not config:
        return {}
    return config.get("settings", {})