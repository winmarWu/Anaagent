"""
Token 消耗监控模块

设计说明：
- 记录每次API调用的token消耗
- 支持按团队、Agent、时间统计
- JSONL 日志文件存储
- CSV 导出功能
- 提供预警功能
"""

import csv
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from anaagent.environment import get_current_environment


def get_logs_dir() -> Path:
    """全局使用统计日志目录（随 Path.home() 解析，便于测试隔离）。"""
    return Path.home() / ".anaagent" / "logs"


@dataclass
class TokenUsage:
    """Token使用记录"""

    timestamp: str
    team_name: str
    agent_name: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost: float
    request_id: str = ""


def ensure_logs_dir():
    """确保日志目录存在"""
    get_logs_dir().mkdir(parents=True, exist_ok=True)


def get_usage_db_path() -> Optional[Path]:
    """获取使用记录数据库路径"""
    env_path = get_current_environment()
    if env_path:
        return env_path / "usage.db"
    return None


def get_global_db_path() -> Path:
    """获取全局使用记录数据库路径"""
    return Path.home() / ".anaagent" / "usage.db"


def init_usage_db():
    """初始化使用记录数据库"""
    db_path = get_usage_db_path()
    if db_path:
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


def init_global_db():
    """初始化全局使用记录数据库"""
    db_path = get_global_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS global_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            date TEXT NOT NULL,
            team_name TEXT NOT NULL,
            agent_name TEXT,
            model TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            total_tokens INTEGER,
            cost REAL,
            request_id TEXT,
            metadata TEXT
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_global_date ON global_usage(date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_global_team ON global_usage(team_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_global_agent ON global_usage(agent_name)")

    conn.commit()
    conn.close()


def record_usage(
    agent_name: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    team_name: str = "",
    metadata: dict = None,
) -> bool:
    """
    记录Token使用

    Args:
        agent_name: Agent名称
        model: 模型名称
        input_tokens: 输入token数
        output_tokens: 输出token数
        team_name: 团队名称（可选，默认使用当前团队）
        metadata: 其他元数据
    """
    # 获取团队名称
    if not team_name:
        env_path = get_current_environment()
        if env_path:
            team_name = env_path.name
        else:
            team_name = "unknown"

    total_tokens = input_tokens + output_tokens
    cost = calculate_cost(model, input_tokens, output_tokens)
    request_id = datetime.now().strftime("%Y%m%d%H%M%S%f")

    # 记录到当前团队数据库
    db_path = get_usage_db_path()
    if db_path:
        init_usage_db()
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

    # 记录到全局数据库
    init_global_db()
    global_db_path = get_global_db_path()
    conn = sqlite3.connect(str(global_db_path))
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO global_usage
        (timestamp, date, team_name, agent_name, model, input_tokens, output_tokens, total_tokens, cost, request_id, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().isoformat(),
        datetime.now().strftime("%Y-%m-%d"),
        team_name,
        agent_name,
        model,
        input_tokens,
        output_tokens,
        total_tokens,
        cost,
        request_id,
        json.dumps(metadata or {})
    ))

    conn.commit()
    conn.close()

    # 写入 JSONL 日志文件
    write_to_jsonl_log(team_name, agent_name, model, input_tokens, output_tokens, cost, request_id)

    return True


def write_to_jsonl_log(
    team_name: str,
    agent_name: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost: float,
    request_id: str,
):
    """写入 JSONL 日志文件"""
    ensure_logs_dir()

    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = get_logs_dir() / f"usage_{date_str}.jsonl"

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "team": team_name,
        "agent": agent_name,
        "model": model,
        "tokens_in": input_tokens,
        "tokens_out": output_tokens,
        "cost": round(cost, 6),
        "request_id": request_id,
    }

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """
    计算费用（美元）

    支持多种模型定价
    """
    # 模型定价配置（每 1M tokens）
    pricing = {
        # Claude 系列
        "claude-opus-4-6": {"input": 0.015, "output": 0.075},
        "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
        "claude-haiku-4-5": {"input": 0.001, "output": 0.005},
        "claude-3-opus": {"input": 0.015, "output": 0.075},
        "claude-3-sonnet": {"input": 0.003, "output": 0.015},
        "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
        # 阿里云百炼
        "qwen": {"input": 0.0005, "output": 0.002},
        "qwen-max": {"input": 0.02, "output": 0.06},
        "qwen-plus": {"input": 0.0004, "output": 0.0012},
        "qwen-turbo": {"input": 0.0002, "output": 0.0006},
        "qwen3.5-plus": {"input": 0.0004, "output": 0.0012},
        # Kimi / 智谱
        "kimi": {"input": 0.012, "output": 0.012},
        "kimi-k2.5": {"input": 0.012, "output": 0.012},
        "glm": {"input": 0.001, "output": 0.001},
        "glm-4": {"input": 0.014, "output": 0.014},
        # DeepSeek
        "deepseek": {"input": 0.0001, "output": 0.0002},
        "deepseek-chat": {"input": 0.0001, "output": 0.0002},
        "deepseek-reasoner": {"input": 0.00055, "output": 0.00219},
        # GPT 系列
        "gpt-4": {"input": 0.03, "output": 0.06},
        "gpt-4-turbo": {"input": 0.01, "output": 0.03},
        "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    }

    # 默认价格（使用 sonnet 档）
    default_price = {"input": 0.003, "output": 0.015}

    # 查找匹配的定价
    price = default_price
    model_lower = model.lower()
    for model_name, p in pricing.items():
        if model_name.lower() in model_lower:
            price = p
            break

    # 计算费用
    input_cost = (input_tokens / 1_000_000) * price["input"]
    output_cost = (output_tokens / 1_000_000) * price["output"]

    return round(input_cost + output_cost, 6)


def get_usage_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    agent_name: Optional[str] = None,
    team_name: Optional[str] = None,
) -> dict:
    """
    获取使用统计

    Args:
        start_date: 开始日期 YYYY-MM-DD
        end_date: 结束日期 YYYY-MM-DD
        agent_name: Agent名称过滤
        team_name: 团队名称过滤（全局统计时使用）
    """
    # 使用全局数据库进行统计
    global_db_path = get_global_db_path()
    if not global_db_path.exists():
        return {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "record_count": 0,
            "records": [],
        }

    conn = sqlite3.connect(str(global_db_path))
    cursor = conn.cursor()

    # 构建查询
    query = "SELECT * FROM global_usage WHERE 1=1"
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

    if team_name:
        query += " AND team_name = ?"
        params.append(team_name)

    query += " ORDER BY timestamp DESC LIMIT 1000"

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
            "team_name": row[3],
            "agent_name": row[4],
            "model": row[5],
            "input_tokens": row[6],
            "output_tokens": row[7],
            "total_tokens": row[8],
            "cost": row[9],
            "request_id": row[10] if len(row) > 10 else "",
        }
        records.append(record)
        total_input += row[6]
        total_output += row[7]
        total_cost += row[9]

    conn.close()

    return {
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_input + total_output,
        "total_cost": round(total_cost, 4),
        "record_count": len(records),
        "records": records[:100],
    }


def get_daily_usage(date: Optional[str] = None) -> dict:
    """获取每日使用统计"""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    return get_usage_stats(start_date=date, end_date=date)


def get_weekly_usage() -> dict:
    """获取本周使用统计"""
    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday())  # 周一
    end_of_week = start_of_week + timedelta(days=6)  # 周日

    return get_usage_stats(
        start_date=start_of_week.strftime("%Y-%m-%d"),
        end_date=end_of_week.strftime("%Y-%m-%d"),
    )


def get_usage_by_agent(team_name: str = None) -> dict:
    """按Agent统计使用量"""
    global_db_path = get_global_db_path()
    if not global_db_path.exists():
        return {}

    conn = sqlite3.connect(str(global_db_path))
    cursor = conn.cursor()

    if team_name:
        cursor.execute("""
            SELECT agent_name,
                   SUM(input_tokens) as total_input,
                   SUM(output_tokens) as total_output,
                   SUM(total_tokens) as total_tokens,
                   SUM(cost) as total_cost,
                   COUNT(*) as call_count
            FROM global_usage
            WHERE team_name = ?
            GROUP BY agent_name
            ORDER BY total_tokens DESC
        """, (team_name,))
    else:
        cursor.execute("""
            SELECT agent_name,
                   SUM(input_tokens) as total_input,
                   SUM(output_tokens) as total_output,
                   SUM(total_tokens) as total_tokens,
                   SUM(cost) as total_cost,
                   COUNT(*) as call_count
            FROM global_usage
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


def get_usage_by_team() -> dict:
    """按团队统计使用量"""
    global_db_path = get_global_db_path()
    if not global_db_path.exists():
        return {}

    conn = sqlite3.connect(str(global_db_path))
    cursor = conn.cursor()

    cursor.execute("""
        SELECT team_name,
               SUM(input_tokens) as total_input,
               SUM(output_tokens) as total_output,
               SUM(total_tokens) as total_tokens,
               SUM(cost) as total_cost,
               COUNT(*) as call_count
        FROM global_usage
        GROUP BY team_name
        ORDER BY total_tokens DESC
    """)

    result = {}
    for row in cursor.fetchall():
        if row[0]:
            result[row[0]] = {
                "input_tokens": row[1],
                "output_tokens": row[2],
                "total_tokens": row[3],
                "cost": round(row[4], 4),
                "call_count": row[5]
            }

    conn.close()
    return result


def get_daily_breakdown(start_date: str, end_date: str) -> list[dict]:
    """获取每日消费明细"""
    global_db_path = get_global_db_path()
    if not global_db_path.exists():
        return []

    conn = sqlite3.connect(str(global_db_path))
    cursor = conn.cursor()

    cursor.execute("""
        SELECT date,
               SUM(input_tokens) as total_input,
               SUM(output_tokens) as total_output,
               SUM(total_tokens) as total_tokens,
               SUM(cost) as total_cost,
               COUNT(*) as call_count
        FROM global_usage
        WHERE date >= ? AND date <= ?
        GROUP BY date
        ORDER BY date ASC
    """, (start_date, end_date))

    result = []
    for row in cursor.fetchall():
        result.append({
            "date": row[0],
            "input_tokens": row[1],
            "output_tokens": row[2],
            "total_tokens": row[3],
            "cost": round(row[4], 4),
            "call_count": row[5]
        })

    conn.close()
    return result


def export_to_csv(start_date: str = None, end_date: str = None, output_path: str = None) -> Path:
    """
    导出使用记录到 CSV

    Args:
        start_date: 开始日期
        end_date: 结束日期
        output_path: 输出路径（可选）

    Returns:
        导出的文件路径
    """
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")

    stats = get_usage_stats(start_date=start_date, end_date=end_date)

    if output_path is None:
        ensure_logs_dir()
        output_path = get_logs_dir() / f"usage_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    output_path = Path(output_path)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "时间", "团队", "Agent", "模型", "输入Tokens", "输出Tokens", "总Tokens", "费用($)"
        ])

        for record in stats["records"]:
            writer.writerow([
                record["timestamp"],
                record["team_name"],
                record["agent_name"],
                record["model"],
                record["input_tokens"],
                record["output_tokens"],
                record["total_tokens"],
                f"{record['cost']:.6f}"
            ])

    return output_path


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


def get_global_usage_totals() -> dict:
    """全局累计：总 token、总费用、总调用次数（来自 global_usage）。"""
    global_db_path = get_global_db_path()
    if not global_db_path.exists():
        return {"total_tokens": 0, "total_cost": 0.0, "api_calls": 0}
    conn = sqlite3.connect(str(global_db_path))
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            COALESCE(SUM(total_tokens), 0),
            COALESCE(SUM(cost), 0),
            COUNT(*)
        FROM global_usage
        """
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {"total_tokens": 0, "total_cost": 0.0, "api_calls": 0}
    return {
        "total_tokens": int(row[0] or 0),
        "total_cost": round(float(row[1] or 0), 4),
        "api_calls": int(row[2] or 0),
    }


def get_dashboard_summary() -> dict:
    """首页/仪表盘：今日与累计统计。"""
    today = get_daily_usage()
    totals = get_global_usage_totals()
    return {
        "today": {
            "total_tokens": today.get("total_tokens", 0),
            "total_cost": today.get("total_cost", 0.0),
            "api_calls": today.get("record_count", 0),
        },
        "all_time": totals,
    }


def get_usage_report() -> str:
    """生成使用报告"""
    today = get_daily_usage()
    by_agent = get_usage_by_agent()
    by_team = get_usage_by_team()

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
        "## Usage by Team",
    ]

    for team, stats in by_team.items():
        lines.append(f"- **{team}**: {stats['total_tokens']:,} tokens, ${stats['cost']:.4f}")

    lines.append("")
    lines.append("## Usage by Agent")

    for agent, stats in by_agent.items():
        lines.append(f"- **{agent}**: {stats['total_tokens']:,} tokens, ${stats['cost']:.4f}")

    return "\n".join(lines)


def format_cost(cost: float) -> str:
    """格式化费用显示"""
    if cost < 0.01:
        return f"${cost * 100:.4f}¢"
    return f"${cost:.2f}"
