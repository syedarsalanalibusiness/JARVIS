import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class MemoryStore:
    """Small SQLite-backed session transcript store for JARVIS."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        self.connection.commit()

    def add(self, session_id: str, role: str, content: str) -> None:
        if not content.strip():
            return
        self.connection.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content.strip(), datetime.now(timezone.utc).isoformat()),
        )
        self.connection.commit()

    def context(self, session_id: str, limit: int = 10) -> list[dict[str, str]]:
        rows = self.connection.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [{"role": role, "content": content} for role, content in reversed(rows)]

    def close(self) -> None:
        self.connection.close()
