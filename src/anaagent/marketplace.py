"""
人才市场模块 - 参考 Anaconda channel 设计

设计说明：
- marketplace/ 目录作为本地市场缓存
- 支持从远程市场安装技能包、Agent模板
- 支持本地打包和发布
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import yaml

from anaagent.environment import ENVS_DIR
from anaagent.models import OperationResult


# 市场目录
MARKETPLACE_DIR = ENVS_DIR.parent / "marketplace"
MARKETPLACE_INDEX = MARKETPLACE_DIR / "index.json"


@dataclass
class MarketItem:
    """市场项目"""
    name: str
    type: str  # skill, agent, hook, mcp
    version: str
    author: str
    description: str
    tags: list
    downloads: int
    source: str  # local or url


def init_marketplace():
    """初始化市场目录"""
    MARKETPLACE_DIR.mkdir(parents=True, exist_ok=True)

    # 创建子目录
    (MARKETPLACE_DIR / "skills").mkdir(exist_ok=True)
    (MARKETPLACE_DIR / "agents").mkdir(exist_ok=True)
    (MARKETPLACE_DIR / "hooks").mkdir(exist_ok=True)
    (MARKETPLACE_DIR / "mcps").mkdir(exist_ok=True)

    # 创建索引文件
    if not MARKETPLACE_INDEX.exists():
        index = {
            "version": "1.0",
            "updated": datetime.now().isoformat(),
            "items": []
        }
        with open(MARKETPLACE_INDEX, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)


def get_marketplace_index() -> dict:
    """获取市场索引"""
    if not MARKETPLACE_INDEX.exists():
        init_marketplace()
        return _get_default_index()

    try:
        with open(MARKETPLACE_INDEX, encoding="utf-8") as f:
            index = json.load(f)
            # 如果items为空，返回默认索引
            if not index.get("items"):
                return _get_default_index()
            return index
    except Exception:
        return _get_default_index()


def _get_default_index() -> dict:
    """获取默认市场索引（内置技能包 + refer目录中的skill/mcp）"""
    items = [
        {
            "name": "react-development",
            "type": "skill",
            "version": "1.0.0",
            "author": "anaagent",
            "description": "React development best practices and patterns",
            "tags": ["react", "frontend", "javascript"],
            "downloads": 0,
            "source": "builtin"
        },
        {
            "name": "python-testing",
            "type": "skill",
            "version": "1.0.0",
            "author": "anaagent",
            "description": "Python testing with pytest and best practices",
            "tags": ["python", "testing", "pytest"],
            "downloads": 0,
            "source": "builtin"
        },
        {
            "name": "code-review",
            "type": "skill",
            "version": "1.0.0",
            "author": "anaagent",
            "description": "Comprehensive code review guidelines",
            "tags": ["review", "quality", "best-practices"],
            "downloads": 0,
            "source": "builtin"
        },
        {
            "name": "api-design",
            "type": "skill",
            "version": "1.0.0",
            "author": "anaagent",
            "description": "RESTful API design and documentation",
            "tags": ["api", "rest", "documentation"],
            "downloads": 0,
            "source": "builtin"
        },
        {
            "name": "git-workflow",
            "type": "skill",
            "version": "1.0.0",
            "author": "anaagent",
            "description": "Git workflow and commit conventions",
            "tags": ["git", "workflow", "version-control"],
            "downloads": 0,
            "source": "builtin"
        },
        {
            "name": "senior-developer",
            "type": "agent",
            "version": "1.0.0",
            "author": "anaagent",
            "description": "Senior developer agent with full-stack expertise",
            "tags": ["developer", "fullstack", "senior"],
            "downloads": 0,
            "source": "builtin"
        },
        {
            "name": "code-reviewer",
            "type": "agent",
            "version": "1.0.0",
            "author": "anaagent",
            "description": "Specialized code reviewer agent",
            "tags": ["reviewer", "quality"],
            "downloads": 0,
            "source": "builtin"
        },
        {
            "name": "pre-commit-check",
            "type": "hook",
            "version": "1.0.0",
            "author": "anaagent",
            "description": "Pre-commit validation hook",
            "tags": ["hook", "pre-commit", "validation"],
            "downloads": 0,
            "source": "builtin"
        },
    ]

    # 扫描 refer/skill 目录
    refer_skill_dir = Path("/app/refer/skill/skills-main/skills")
    if refer_skill_dir.exists():
        for skill_dir in refer_skill_dir.iterdir():
            if skill_dir.is_dir():
                skill_md = skill_dir / "SKILL.md"
                if skill_md.exists():
                    # 解析SKILL.md的frontmatter
                    desc = skill_dir.name.replace("-", " ").title()
                    try:
                        content = skill_md.read_text(encoding="utf-8")
                        if content.startswith("---"):
                            parts = content.split("---", 2)
                            if len(parts) >= 3:
                                import yaml
                                fm = yaml.safe_load(parts[1])
                                desc = fm.get("description", desc)[:80]
                    except Exception:
                        pass

                    items.append({
                        "name": skill_dir.name,
                        "type": "skill",
                        "version": "1.0.0",
                        "author": "anthropic",
                        "description": desc,
                        "tags": ["official", "claude-code"],
                        "downloads": 0,
                        "source": "refer"
                    })

    # 扫描 refer/mcp 目录
    refer_mcp_dir = Path("/app/refer/mcp/servers-main/src")
    if refer_mcp_dir.exists():
        for mcp_dir in refer_mcp_dir.iterdir():
            if mcp_dir.is_dir():
                readme = mcp_dir / "README.md"
                desc = mcp_dir.name.replace("-", " ").title()
                if readme.exists():
                    try:
                        content = readme.read_text(encoding="utf-8")
                        # 提取第一行作为描述
                        for line in content.split("\n"):
                            if line.strip() and not line.startswith("#"):
                                desc = line.strip()[:80]
                                break
                    except Exception:
                        pass

                items.append({
                    "name": mcp_dir.name,
                    "type": "mcp",
                    "version": "1.0.0",
                    "author": "anthropic",
                    "description": desc,
                    "tags": ["official", "mcp-server"],
                    "downloads": 0,
                    "source": "refer"
                })

    return {
        "version": "1.0",
        "updated": datetime.now().isoformat(),
        "items": items
    }


def search_market(query: str, item_type: Optional[str] = None) -> list[dict]:
    """
    搜索市场

    Args:
        query: 搜索关键词
        item_type: 类型过滤 (skill, agent, hook, mcp)

    Returns:
        匹配的市场项目列表
    """
    index = get_marketplace_index()
    items = index.get("items", [])

    results = []
    query_lower = query.lower()

    for item in items:
        # 类型过滤
        if item_type and item.get("type") != item_type:
            continue

        # 搜索匹配
        name = item.get("name", "").lower()
        desc = item.get("description", "").lower()
        tags = [t.lower() for t in item.get("tags", [])]

        # 匹配名称、描述或标签
        if (query_lower in name or
            query_lower in desc or
            any(query_lower in tag for tag in tags)):
            results.append(item)

    return results


def list_market(item_type: Optional[str] = None) -> list[dict]:
    """列出市场项目"""
    index = get_marketplace_index()
    items = index.get("items", [])

    if item_type:
        return [i for i in items if i.get("type") == item_type]

    return items


def install_from_market(name: str, item_type: str) -> OperationResult:
    """
    从市场安装组件

    Args:
        name: 组件名称
        item_type: 类型 (skill, agent, hook, mcp)
    """
    from anaagent.component_manager import install_skill, install_hook
    from anaagent.agent_manager import add_agent

    index = get_marketplace_index()
    items = index.get("items", [])

    # 查找项目
    item = None
    for i in items:
        if i.get("name") == name and i.get("type") == item_type:
            item = i
            break

    if not item:
        return OperationResult(
            success=False,
            message=f"'{name}' not found in marketplace"
        )

    # 根据类型安装
    if item_type == "skill":
        result = _install_builtin_skill(name, item)
    elif item_type == "agent":
        result = _install_builtin_agent(name, item)
    elif item_type == "hook":
        result = _install_builtin_hook(name, item)
    else:
        result = OperationResult(success=False, message=f"Unsupported type: {item_type}")

    # 更新下载计数
    if result.success:
        for i in items:
            if i.get("name") == name:
                i["downloads"] = i.get("downloads", 0) + 1
                break
        index["items"] = items
        with open(MARKETPLACE_INDEX, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

    return result


def _install_builtin_skill(name: str, item: dict) -> OperationResult:
    """安装内置技能包"""
    from anaagent.component_manager import install_skill

    # 先用模板创建
    result = install_skill(name)

    if result.success:
        # 更新 SKILL.md 内容
        skill_md = result.path / "SKILL.md"
        content = f'''---
name: {name}
description: {item.get("description", "")}
version: {item.get("version", "1.0.0")}
author: {item.get("author", "anaagent")}
dependencies: []
triggers:
  - {name}
  - {", ".join(item.get("tags", [])[:3])}
---

# {name} Skill

{item.get("description", "")}

## Role Definition
You are an expert in {name}.

## Capabilities
- Capability 1
- Capability 2
- Capability 3

## Best Practices
1. Practice 1
2. Practice 2
3. Practice 3

## Output Standards
Provide clear, well-structured output following industry best practices.
'''
        skill_md.write_text(content, encoding="utf-8")

    return result


def _install_builtin_agent(name: str, item: dict) -> OperationResult:
    """安装内置Agent模板"""
    from anaagent.agent_manager import add_agent

    role = name.replace("-", "_")
    return add_agent(
        name=name,
        role=role,
        description=item.get("description", "")
    )


def _install_builtin_hook(name: str, item: dict) -> OperationResult:
    """安装内置Hook"""
    from anaagent.component_manager import install_hook

    return install_hook(f"{name}.py")


def publish_to_market(
    name: str,
    item_type: str,
    source_path: str,
    description: str = "",
    author: str = "local",
    tags: list = None
) -> OperationResult:
    """
    发布组件到本地市场

    Args:
        name: 组件名称
        item_type: 类型
        source_path: 源路径
        description: 描述
        author: 作者
        tags: 标签列表
    """
    init_marketplace()

    source = Path(source_path)
    if not source.exists():
        return OperationResult(success=False, message=f"Source path not found: {source_path}")

    # 目标目录
    target_dir = MARKETPLACE_DIR / f"{item_type}s"
    target_path = target_dir / name

    try:
        # 复制文件
        if source.is_dir():
            if target_path.exists():
                shutil.rmtree(target_path)
            shutil.copytree(source, target_path)
        else:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target_path)

        # 更新索引
        index = get_marketplace_index()
        items = index.get("items", [])

        # 检查是否已存在
        existing = False
        for i in items:
            if i.get("name") == name and i.get("type") == item_type:
                i["version"] = "1.0.0"
                i["description"] = description
                i["author"] = author
                i["tags"] = tags or []
                i["updated"] = datetime.now().isoformat()
                existing = True
                break

        if not existing:
            items.append({
                "name": name,
                "type": item_type,
                "version": "1.0.0",
                "author": author,
                "description": description,
                "tags": tags or [],
                "downloads": 0,
                "source": "local"
            })

        index["items"] = items
        index["updated"] = datetime.now().isoformat()

        with open(MARKETPLACE_INDEX, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

        return OperationResult(success=True, path=target_path)

    except Exception as e:
        return OperationResult(success=False, message=str(e))