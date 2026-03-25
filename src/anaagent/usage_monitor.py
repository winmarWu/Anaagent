"""
Token 消耗监控模块

设计说明：
- 记录每次API调用的token消耗
- 支持按团队、Agent、时间统计
- 提供预警功能
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from anaagent.environment import get_current_environment


@dataclass
class TokenUsage:
    """Token使用记录"""
    timestamp: str
    agent_name: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost: float


def get_usage_db_path() -> Optional[Path]:
    """获取使用记录数据库路径"""
    env_path = get_current_environment()
    if env_path:
        return env_path / "usage.db"
    return None


def init_usage_db():
    """初始化使用记录数据库"""
    db_path = get_usage_db_path()
    if not db_path:
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS token_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            date TEXT NOT NULL,
            agent_name TEXT,
            model TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            total_tokens INTEGER,
            cost REAL,
            metadata TEXT
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_date ON token_usage(date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_agent ON token_usage(agent_name)")

    conn.commit()
    conn.close()


def record_usage(
    agent_name: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    metadata: dict = None
) -> bool:
    """
    记录Token使用

    Args:
        agent_name: Agent名称
        model: 模型名称
        input_tokens: 输入token数
        output_tokens: 输出token数
        metadata: 其他元数据
    """
    db_path = get_usage_db_path()
    if not db_path:
        return False

    init_usage_db()

    total_tokens = input_tokens + output_tokens
    cost = calculate_cost(model, input_tokens, output_tokens)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO token_usage
        (timestamp, date, agent_name, model, input_tokens, output_tokens, total_tokens, cost, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().isoformat(),
        datetime.now().strftime("%Y-%m-%d"),
        agent_name,
        model,
        input_tokens,
        output_tokens,
        total_tokens,
        cost,
        json.dumps(metadata or {})
    ))

    conn.commit()
    conn.close()

    return True


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """
    计算费用（美元）

    参考 Claude 定价（2024年）
    """
    pricing = {
        "claude-opus-4-6": {"input": 0.015, "output": 0.075},
        "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
        "claude-haiku-4-5": {"input": 0.001, "output": 0.005},
        "claude-3-opus": {"input": 0.015, "output": 0.075},
        "claude-3-sonnet": {"input": 0.003, "output": 0.015},
        "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
    }

    # 默认使用 sonnet 价格
    default_price = {"input": 0.003, "output": 0.015}

    # 查找匹配的定价
    price = default_price
    for model_name, p in pricing.items():
        if model_name.lower() in model.lower():
            price = p
            break

    # 计算费用（每1M tokens）
    input_cost = (input_tokens / 1_000_000) * price["input"]
    output_cost = (output_tokens / 1_000_000) * price["output"]

    return round(input_cost + output_cost, 6)


def get_usage_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    agent_name: Optional[str] = None
) -> dict:
    """
    获取使用统计

    Args:
        start_date: 开始日期 YYYY-MM-DD
        end_date: 结束日期 YYYY-MM-DD
        agent_name: Agent名称过滤
    """
    db_path = get_usage_db_path()
    if not db_path or not db_path.exists():
        return {"total_tokens": 0, "total_cost": 0, "records": []}

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # 构建查询
    query = "SELECT * FROM token_usage WHERE 1=1"
    params = []

    if start_date:
        query += " AND date >= ?"
        params.append(start_date)

    if end_date:
        query += " AND date <= ?"
        params.append(end_date)

    if agent_name:
        query += " AND agent_name = ?"
        params.append(agent_name)

    query += " ORDER BY timestamp DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    # 统计
    total_input = 0
    total_output = 0
    total_cost = 0.0
    records = []

    for row in rows:
        record = {
            "id": row[0],
            "timestamp": row[1],
            "date": row[2],
            "agent_name": row[3],
            "model": row[4],
            "input_tokens": row[5],
            "output_tokens": row[6],
            "total_tokens": row[7],
            "cost": row[8],
        }
        records.append(record)
        total_input += row[5]
        total_output += row[6]
        total_cost += row[8]

    conn.close()

    return {
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_input + total_output,
        "total_cost": round(total_cost, 4),
        "record_count": len(records),
        "records": records[:100]  # 最多返回100条
    }


def get_daily_usage(date: Optional[str] = None) -> dict:
    """获取每日使用统计"""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    return get_usage_stats(start_date=date, end_date=date)


def get_usage_by_agent() -> dict:
    """按Agent统计使用量"""
    db_path = get_usage_db_path()
    if not db_path or not db_path.exists():
        return {}

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        SELECT agent_name,
               SUM(input_tokens) as total_input,
               SUM(output_tokens) as total_output,
               SUM(total_tokens) as total_tokens,
               SUM(cost) as total_cost,
               COUNT(*) as call_count
        FROM token_usage
        GROUP BY agent_name
        ORDER BY total_tokens DESC
    """)

    result = {}
    for row in cursor.fetchall():
        if row[0]:  # agent_name not null
            result[row[0]] = {
                "input_tokens": row[1],
                "output_tokens": row[2],
                "total_tokens": row[3],
                "cost": round(row[4], 4),
                "call_count": row[5]
            }

    conn.close()
    return result


def check_usage_limit(limit_tokens: int) -> tuple[bool, int]:
    """
    检查是否超过限制

    Args:
        limit_tokens: 每日限制

    Returns:
        (是否超限, 今日已使用)
    """
    today_usage = get_daily_usage()
    used = today_usage.get("total_tokens", 0)

    return used >= limit_tokens, used


def get_usage_report() -> str:
    """生成使用报告"""
    today = get_daily_usage()
    by_agent = get_usage_by_agent()

    lines = [
        "# Token Usage Report",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Today's Usage",
        f"- Total Tokens: {today['total_tokens']:,}",
        f"- Input Tokens: {today['total_input_tokens']:,}",
        f"- Output Tokens: {today['total_output_tokens']:,}",
        f"- Cost: ${today['total_cost']:.4f}",
        f"- API Calls: {today['record_count']}",
        "",
        "## Usage by Agent",
    ]

    for agent, stats in by_agent.items():
        lines.append(f"- **{agent}**: {stats['total_tokens']:,} tokens, ${stats['cost']:.4f}")

    return "\n".join(lines)