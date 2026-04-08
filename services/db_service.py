import sqlite3
from config import DB_PATH


def init_db():
    """Создаёт таблицу и применяет миграции."""
    db = sqlite3.connect(DB_PATH)
    db.execute("""
        CREATE TABLE IF NOT EXISTS нормы (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            деталь TEXT NOT NULL,
            операция TEXT NOT NULL,
            t_шт_предложено REAL,
            t_шт_подтверждено REAL,
            t_пз_предложено REAL,
            t_пз_подтверждено REAL,
            режимы TEXT,
            обоснование TEXT,
            дата TEXT,
            подтверждено INTEGER DEFAULT 0
        )
    """)
    for col in ("режимы TEXT", "изделие TEXT", "оборудование TEXT"):
        try:
            db.execute(f"ALTER TABLE нормы ADD COLUMN {col}")
        except Exception:
            pass
    db.execute("""
        CREATE TABLE IF NOT EXISTS метрики_прогонов (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            дата TEXT NOT NULL,
            деталь TEXT,
            входные_токены INTEGER DEFAULT 0,
            выходные_токены INTEGER DEFAULT 0,
            всего_токенов INTEGER DEFAULT 0,
            время_мс INTEGER DEFAULT 0,
            вызовов_llm INTEGER DEFAULT 0,
            этапы_json TEXT
        )
    """)
    db.commit()
    db.close()


def get_connection():
    """Создаёт новое соединение с row_factory = sqlite3.Row."""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db
