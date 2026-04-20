"""团队模板模块"""

from pathlib import Path
from typing import Optional

import yaml

from anaagent.models import TeamTemplate


def get_templates_dir() -> Path:
    """获取模板目录"""
    return Path(__file__).parent


def list_templates() -> list[str]:
    """列出所有可用模板"""
    templates_dir = get_templates_dir()
    templates = []
    for template_file in templates_dir.glob("*.yaml"):
        templates.append(template_file.stem)
    return templates


def load_template(name: str) -> Optional[TeamTemplate]:
    """加载指定模板"""
    template_path = get_templates_dir() / f"{name}.yaml"
    if not template_path.exists():
        return None

    with open(template_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return TeamTemplate(**data)


def get_template_info(name: str) -> dict:
    """获取模板信息"""
    template = load_template(name)
    if not template:
        return {}

    return {
        "name": template.name,
        "description": template.description,
        "agent_count": len(template.agents),
        "agents": [a.get("name", "") for a in template.agents],
    }
