"""数据库模块 - SQLite + sqlite-vec 向量存储"""

import sqlite3
from pathlib import Path
from typing import Optional


def init_database(db_path: Path):
    """
    初始化SQLite数据库，包含向量扩展

    设计说明：
    - 使用 sqlite-vec 扩展支持向量相似度检索
    - 存储记忆内容的向量嵌入
    - 用于语义搜索和记忆召回
    """
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # 创建记忆表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            embedding BLOB,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            importance REAL DEFAULT 0.5
        )
    """)

    # 创建技能表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            embedding BLOB,
            triggers TEXT
        )
    """)

    # 创建对话历史表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT,
            role TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 创建索引
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_agent ON conversations(agent_name)")

    conn.commit()
    conn.close()


def get_connection(db_path: Path) -> sqlite3.Connection:
    """获取数据库连接"""
    conn = sqlite3.connect(str(db_path))
    # 启用外键约束
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def add_memory(db_path: Path, content: str, metadata: str = "", importance: float = 0.5) -> int:
    """
    添加一条记忆

    Args:
        content: 记忆内容
        metadata: 元数据（JSON格式）
        importance: 重要性分数 (0-1)

    Returns:
        新记录的ID
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO memories (content, metadata, importance) VALUES (?, ?, ?)",
        (content, metadata, importance),
    )
    memory_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return memory_id


def search_memories(db_path: Path, query: str, limit: int = 10) -> list[dict]:
    """
    搜索记忆（基础文本搜索）

    后续会集成向量相似度搜索
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, content, metadata, importance, created_at
        FROM memories
        WHERE content LIKE ?
        ORDER BY importance DESC, created_at DESC
        LIMIT ?
        """,
        (f"%{query}%", limit),
    )

    results = [
        {
            "id": row[0],
            "content": row[1],
            "metadata": row[2],
            "importance": row[3],
            "created_at": row[4],
        }
        for row in cursor.fetchall()
    ]

    conn.close()
    return results


def get_recent_memories(db_path: Path, limit: int = 20) -> list[dict]:
    """获取最近的记忆"""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, content, metadata, importance, created_at
        FROM memories
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    )

    results = [
        {
            "id": row[0],
            "content": row[1],
            "metadata": row[2],
            "importance": row[3],
            "created_at": row[4],
        }
        for row in cursor.fetchall()
    ]

    conn.close()
    return results