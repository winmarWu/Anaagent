"""
团队导出/导入模块

设计说明：
- 支持将团队配置打包为可分享的文件
- 支持从包导入团队
- 参考 conda pack 设计
"""

import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from anaagent.environment import ENVS_DIR, get_current_environment, activate_environment
from anaagent.models import OperationResult


def export_team(
    team_name: str,
    output_path: Optional[str] = None,
    include_memory: bool = False,
    include_api_keys: bool = False
) -> OperationResult:
    """
    导出团队配置

    Args:
        team_name: 团队名称
        output_path: 输出路径，默认当前目录
        include_memory: 是否包含记忆数据
        include_api_keys: 是否包含API密钥
    """
    team_path = ENVS_DIR / team_name
    if not team_path.exists():
        return OperationResult(success=False, message=f"Team '{team_name}' not found")

    # 输出文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{team_name}_{timestamp}.anaagent"
    output_file = Path(output_path) / filename if output_path else Path(filename)

    try:
        with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            # 添加元数据
            metadata = {
                "version": "1.0",
                "team_name": team_name,
                "exported_at": datetime.now().isoformat(),
                "include_memory": include_memory,
                "include_api_keys": include_api_keys
            }
            zf.writestr(".metadata.json", json.dumps(metadata, indent=2))

            # 遍历团队目录
            for item in team_path.rglob("*"):
                if item.is_file():
                    # 跳过不需要的文件
                    rel_path = item.relative_to(team_path)

                    # 跳过数据库文件
                    if item.suffix == ".db":
                        if not include_memory:
                            continue

                    # 处理API密钥
                    if item.name == "team.yaml":
                        with open(item, encoding="utf-8") as f:
                            team_config = yaml.safe_load(f)

                        if not include_api_keys and "api_keys" in team_config:
                            team_config["api_keys"] = {}

                        zf.writestr(str(rel_path), yaml.dump(team_config, allow_unicode=True))
                        continue

                    # 添加文件
                    zf.write(item, str(rel_path))

        return OperationResult(success=True, path=output_file)

    except Exception as e:
        return OperationResult(success=False, message=str(e))


def import_team(
    package_path: str,
    new_name: Optional[str] = None,
    overwrite: bool = False
) -> OperationResult:
    """
    导入团队配置

    Args:
        package_path: 包文件路径
        new_name: 新团队名称
        overwrite: 是否覆盖已存在的团队
    """
    package_file = Path(package_path)
    if not package_file.exists():
        return OperationResult(success=False, message=f"Package not found: {package_path}")

    try:
        with zipfile.ZipFile(package_file, 'r') as zf:
            # 读取元数据
            try:
                metadata_str = zf.read(".metadata.json").decode("utf-8")
                metadata = json.loads(metadata_str)
            except Exception:
                metadata = {"team_name": package_file.stem.split("_")[0]}

            # 确定团队名称
            team_name = new_name or metadata.get("team_name", "imported_team")
            team_path = ENVS_DIR / team_name

            # 检查是否已存在
            if team_path.exists() and not overwrite:
                return OperationResult(
                    success=False,
                    message=f"Team '{team_name}' already exists. Use --overwrite to replace."
                )

            # 解压
            team_path.mkdir(parents=True, exist_ok=True)

            for item in zf.namelist():
                if item == ".metadata.json":
                    continue

                # 安全检查：防止路径遍历
                if ".." in item or item.startswith("/"):
                    continue

                target = team_path / item
                target.parent.mkdir(parents=True, exist_ok=True)

                with zf.open(item) as src, open(target, 'wb') as dst:
                    dst.write(src.read())

        return OperationResult(success=True, path=team_path)

    except Exception as e:
        return OperationResult(success=False, message=str(e))


def clone_team(
    source_name: str,
    new_name: str
) -> OperationResult:
    """
    克隆团队

    Args:
        source_name: 源团队名称
        new_name: 新团队名称
    """
    source_path = ENVS_DIR / source_name
    if not source_path.exists():
        return OperationResult(success=False, message=f"Team '{source_name}' not found")

    target_path = ENVS_DIR / new_name
    if target_path.exists():
        return OperationResult(success=False, message=f"Team '{new_name}' already exists")

    try:
        # 复制目录
        shutil.copytree(source_path, target_path)

        # 更新 team.yaml
        team_yaml = target_path / "team.yaml"
        if team_yaml.exists():
            with open(team_yaml, encoding="utf-8") as f:
                config = yaml.safe_load(f)

            config["name"] = new_name
            config["activated"] = False

            # 清除API密钥
            config["api_keys"] = {}

            with open(team_yaml, "w", encoding="utf-8") as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

        return OperationResult(success=True, path=target_path)

    except Exception as e:
        return OperationResult(success=False, message=str(e))


def get_team_info(team_name: str) -> dict:
    """获取团队详细信息"""
    team_path = ENVS_DIR / team_name
    if not team_path.exists():
        return {}

    info = {
        "name": team_name,
        "path": str(team_path),
    }

    # 读取配置
    team_yaml = team_path / "team.yaml"
    if team_yaml.exists():
        with open(team_yaml, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        info.update(config)

    # 统计组件数量
    info["agent_count"] = len(list((team_path / "agents").glob("*.yaml"))) if (team_path / "agents").exists() else 0
    info["skill_count"] = len(list((team_path / "skills").iterdir())) if (team_path / "skills").exists() else 0
    info["hook_count"] = len(list((team_path / "hooks").iterdir())) if (team_path / "hooks").exists() else 0
    info["mcp_count"] = len(list((team_path / "mcps").glob("*.yaml"))) if (team_path / "mcps").exists() else 0
    info["command_count"] = len(list((team_path / "commands").glob("*.md"))) if (team_path / "commands").exists() else 0

    # 计算目录大小
    total_size = sum(f.stat().st_size for f in team_path.rglob("*") if f.is_file())
    info["size_kb"] = round(total_size / 1024, 2)

    return info