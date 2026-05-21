# ── DB 연결 및 초기화 ──

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / 'keepit.db'


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            url         TEXT NOT NULL,
            title       TEXT,
            category    TEXT,
            subcategory TEXT,
            summary     TEXT,
            content_type TEXT,
            tags        TEXT,
            deadline    TEXT,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# SQLite DB 연결 반환 및 items 테이블 초기화
