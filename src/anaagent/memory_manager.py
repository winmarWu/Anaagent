"""记忆系统 - 参考 OpenClaw Memory 设计"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from anaagent.environment import get_current_environment
from anaagent.database import add_memory, get_recent_memories, search_memories


def get_memory_dir() -> Optional[Path]:
    """获取memory目录"""
    env_path = get_current_environment()
    if env_path:
        return env_path / "memory"
    return None


def get_memory_md_path() -> Optional[Path]:
    """获取MEMORY.md路径"""
    memory_dir = get_memory_dir()
    if memory_dir:
        return memory_dir / "MEMORY.md"
    return None


def get_daily_log_path(date: Optional[str] = None) -> Optional[Path]:
    """
    获取每日日志路径

    Args:
        date: 日期字符串 YYYY-MM-DD，默认今天
    """
    memory_dir = get_memory_dir()
    if not memory_dir:
        return None

    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    return memory_dir / "memory" / f"{date}.md"


def add_to_memory(
    content: str,
    category: str = "note",
    importance: float = 0.5
) -> bool:
    """
    添加记忆

    Args:
        content: 记忆内容
        category: 分类 (decision, preference, note, fact)
        importance: 重要性 0-1

    Returns:
        是否成功
    """
    memory_dir = get_memory_dir()
    if not memory_dir:
        return False

    # 1. 写入SQLite数据库
    db_path = memory_dir / "memory.db"
    metadata = f'{{"category": "{category}", "date": "{datetime.now().strftime("%Y-%m-%d")}"}}'
    add_memory(db_path, content, metadata, importance)

    # 2. 追加到每日日志
    daily_log = get_daily_log_path()
    if daily_log:
        daily_log.parent.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%H:%M")
        entry = f"- [{timestamp}] [{category}] {content}\n"

        # 如果文件不存在，创建标题
        if not daily_log.exists():
            date_str = datetime.now().strftime("%Y-%m-%d")
            daily_log.write_text(f"# Daily Log: {date_str}\n\n{entry}", encoding="utf-8")
        else:
            with open(daily_log, "a", encoding="utf-8") as f:
                f.write(entry)

    # 3. 如果重要性高，追加到MEMORY.md
    if importance >= 0.8:
        append_to_long_term_memory(content, category)

    return True


def append_to_long_term_memory(content: str, category: str = "note"):
    """
    追加到长期记忆 MEMORY.md

    根据category决定追加到哪个section
    """
    memory_md = get_memory_md_path()
    if not memory_md:
        return

    if not memory_md.exists():
        # 创建默认结构
        default_content = f"""# Team Memory

## Important Decisions

## Preferences

## Key Facts

"""
        memory_md.write_text(default_content, encoding="utf-8")

    # 读取现有内容
    lines = memory_md.read_text(encoding="utf-8").split("\n")

    # 找到对应的section
    section_map = {
        "decision": "Important Decisions",
        "preference": "Preferences",
        "fact": "Key Facts",
    }
    section_name = section_map.get(category, "Key Facts")

    # 在对应section下添加条目
    new_lines = []
    inserted = False

    for i, line in enumerate(lines):
        new_lines.append(line)
        if line.strip() == f"## {section_name}" and not inserted:
            # 在下一个 ## 之前插入
            for j in range(i + 1, len(lines)):
                if lines[j].startswith("## "):
                    # 在这里插入
                    new_lines.append(f"- {content}")
                    inserted = True
                    break
                elif lines[j].strip() and not lines[j].startswith("-"):
                    continue

            if not inserted:
                # section在文件末尾
                new_lines.append(f"- {content}")
                inserted = True

    if inserted:
        memory_md.write_text("\n".join(new_lines), encoding="utf-8")


def recall_memory(query: str, limit: int = 10) -> list[dict]:
    """
    召回记忆

    Args:
        query: 搜索关键词
        limit: 返回数量限制

    Returns:
        匹配的记忆列表
    """
    memory_dir = get_memory_dir()
    if not memory_dir:
        return []

    db_path = memory_dir / "memory.db"
    return search_memories(db_path, query, limit)


def get_memory_context() -> str:
    """
    获取记忆上下文

    返回 MEMORY.md + 今天的日志 + 昨天的日志
    用于注入到CLAUDE.md或提示词中
    """
    context_parts = []

    # 1. 长期记忆
    memory_md = get_memory_md_path()
    if memory_md and memory_md.exists():
        context_parts.append("## Long-term Memory")
        context_parts.append(memory_md.read_text(encoding="utf-8"))

    # 2. 今天的日志
    today_log = get_daily_log_path()
    if today_log and today_log.exists():
        context_parts.append("\n## Today's Log")
        context_parts.append(today_log.read_text(encoding="utf-8"))

    # 3. 昨天的日志
    from datetime import timedelta
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_log = get_daily_log_path(yesterday)
    if yesterday_log and yesterday_log.exists():
        context_parts.append("\n## Yesterday's Log")
        context_parts.append(yesterday_log.read_text(encoding="utf-8"))

    return "\n".join(context_parts)


def summarize_day() -> str:
    """
    总结今天的日志

    可以在每天结束时调用，生成摘要
    """
    today_log = get_daily_log_path()
    if not today_log or not today_log.exists():
        return "No log for today"

    content = today_log.read_text(encoding="utf-8")

    # 简单统计
    lines = [l for l in content.split("\n") if l.strip().startswith("-")]

    categories = {}
    for line in lines:
        if "[" in line:
            parts = line.split("]")
            if len(parts) >= 2:
                cat = parts[-2].strip().lstrip("[")
                categories[cat] = categories.get(cat, 0) + 1

    summary = f"Today's Summary ({datetime.now().strftime('%Y-%m-%d')}):\n"
    summary += f"- Total entries: {len(lines)}\n"
    for cat, count in categories.items():
        summary += f"- {cat}: {count}\n"

    return summary