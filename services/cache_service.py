"""Кэширование результатов этапов конвейера по хэшу входных файлов.

Кэш живёт в памяти процесса + на диске (SQLite).
При перезапуске — диск-кэш сохраняется.
"""

import hashlib
import json
import sqlite3
import os
from typing import Optional

from config import BASE_DIR

_CACHE_DB = os.path.join(BASE_DIR, "cache.db")
_MEM_CACHE: dict[str, dict] = {}


def _get_db():
    db = sqlite3.connect(_CACHE_DB)
    db.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            stage TEXT NOT NULL,
            data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    return db


def file_hash(file_obj) -> str:
    """Считает SHA-256 хэш от содержимого файла (file-like или строка-путь)."""
    h = hashlib.sha256()
    if isinstance(file_obj, str):
        with open(file_obj, "rb") as f:
            h.update(f.read())
    elif hasattr(file_obj, "read"):
        pos = file_obj.tell() if hasattr(file_obj, "tell") else 0
        data = file_obj.read()
        h.update(data)
        file_obj.seek(pos)
    return h.hexdigest()


def make_key(stage: str, *parts: str) -> str:
    """Составной ключ: stage + хэши файлов."""
    return f"{stage}:" + ":".join(parts)


def get(key: str) -> Optional[dict]:
    """Получить из кэша (сначала память, потом диск)."""
    if key in _MEM_CACHE:
        print(f"[CACHE HIT mem] {key[:60]}", flush=True)
        return _MEM_CACHE[key]

    try:
        db = _get_db()
        row = db.execute("SELECT data FROM cache WHERE key = ?", (key,)).fetchone()
        db.close()
        if row:
            data = json.loads(row[0])
            _MEM_CACHE[key] = data
            print(f"[CACHE HIT disk] {key[:60]}", flush=True)
            return data
    except Exception as e:
        print(f"[CACHE] Ошибка чтения: {e}", flush=True)

    return None


def put(key: str, stage: str, data: dict):
    """Записать в кэш (память + диск)."""
    _MEM_CACHE[key] = data
    try:
        db = _get_db()
        db.execute(
            "INSERT OR REPLACE INTO cache (key, stage, data) VALUES (?, ?, ?)",
            (key, stage, json.dumps(data, ensure_ascii=False)),
        )
        db.commit()
        db.close()
        print(f"[CACHE PUT] {key[:60]}", flush=True)
    except Exception as e:
        print(f"[CACHE] Ошибка записи: {e}", flush=True)


