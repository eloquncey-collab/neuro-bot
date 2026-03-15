import sqlite3
import asyncio
from typing import List, Dict, Optional

class Database:
    def __init__(self, db_name: str = "bot_data.db"):
        self.db_name = db_name
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Таблица для промптов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prompts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    text TEXT NOT NULL,
                    is_active INTEGER DEFAULT 0
                )
            """)
            # Таблица для каналов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT NOT NULL UNIQUE,
                    title TEXT
                )
            """)
            conn.commit()

    async def add_prompt(self, name: str, text: str):
        with self._get_connection() as conn:
            conn.execute("INSERT INTO prompts (name, text) VALUES (?, ?)", (name, text))
            conn.commit()

    async def get_active_prompt(self) -> Optional[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT text FROM prompts WHERE is_active = 1 LIMIT 1")
            row = cursor.fetchone()
            return row['text'] if row else None

    async def set_active_prompt(self, prompt_id: int):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Сначала сбрасываем все
            cursor.execute("UPDATE prompts SET is_active = 0")
            # Активируем нужный
            cursor.execute("UPDATE prompts SET is_active = 1 WHERE id = ?", (prompt_id,))
            conn.commit()

    async def list_prompts(self) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, is_active FROM prompts")
            return [dict(row) for row in cursor.fetchall()]

    async def add_channel(self, channel_id: str, title: str = "Unknown"):
        with self._get_connection() as conn:
            try:
                conn.execute("INSERT OR IGNORE INTO channels (channel_id, title) VALUES (?, ?)", (channel_id, title))
                conn.commit()
            except Exception as e:
                print(f"Error adding channel: {e}")

    async def get_channels(self) -> List[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT channel_id FROM channels")
            return [row['channel_id'] for row in cursor.fetchall()]

# Глобальный экземпляр БД
db = Database()