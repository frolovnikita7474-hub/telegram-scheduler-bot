"""Хранилище запланированных постов"""
import sqlite3
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass

@dataclass
class ScheduledPost:
    id: int
    chat_id: int
    content: str
    file_id: Optional[str]
    file_type: Optional[str]
    scheduled_time: datetime
    status: str

class Database:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                content TEXT,
                file_id TEXT,
                file_type TEXT,
                scheduled_time TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def add_post(self, chat_id: int, content: str, file_id: Optional[str],
                 file_type: Optional[str], scheduled_time: datetime) -> int:
        cursor = self.conn.execute("""
            INSERT INTO scheduled_posts (chat_id, content, file_id, file_type, scheduled_time)
            VALUES (?, ?, ?, ?, ?)
        """, (chat_id, content, file_id, file_type, scheduled_time.isoformat()))
        self.conn.commit()
        return cursor.lastrowid

    def get_due_posts(self) -> List[ScheduledPost]:
        now = datetime.now().isoformat()
        cursor = self.conn.execute("""
            SELECT * FROM scheduled_posts
            WHERE status = 'pending' AND scheduled_time <= ?
            ORDER BY scheduled_time
        """, (now,))
        return [ScheduledPost(**dict(row)) for row in cursor.fetchall()]

    def mark_post_sent(self, post_id: int):
        self.conn.execute("UPDATE scheduled_posts SET status='sent' WHERE id=?", (post_id,))
        self.conn.commit()

    def get_pending(self, chat_id: int) -> List[ScheduledPost]:
        cursor = self.conn.execute("""
            SELECT * FROM scheduled_posts
            WHERE chat_id=? AND status='pending'
            ORDER BY scheduled_time
        """, (chat_id,))
        return [ScheduledPost(**dict(row)) for row in cursor.fetchall()]

    def delete_post(self, post_id: int):
        self.conn.execute("DELETE FROM scheduled_posts WHERE id=?", (post_id,))
        self.conn.commit()