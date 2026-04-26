"""Репозиторий операций: загрузка из Excel, описания и условия применения."""

from __future__ import annotations
import os
from typing import Optional

try:
    import openpyxl
    _OPENPYXL = True
except ImportError:
    _OPENPYXL = False

from config import OPERATIONS_XLSX


# ─── Структура операции ────────────────────────────────────────────────────────

class OperationInfo:
    """Описание операции из справочника."""

    def __init__(self, number: int, name: str, description: str, applicability: str, restrictions: str):
        self.number = number
        self.name = name
        self.description = description
        self.applicability = applicability
        self.restrictions = restrictions

    def __repr__(self):
        return f"OperationInfo({self.name!r})"


# ─── Кеш ──────────────────────────────────────────────────────────────────────

_OPERATIONS: list[OperationInfo] | None = None
_BY_NAME: dict[str, OperationInfo] | None = None


def _load():
    global _OPERATIONS, _BY_NAME

    if not _OPENPYXL:
        _OPERATIONS = []
        _BY_NAME = {}
        return

    if not os.path.exists(OPERATIONS_XLSX):
        print(f"[ПРЕДУПРЕЖДЕНИЕ] Справочник операций не найден: {OPERATIONS_XLSX}", flush=True)
        _OPERATIONS = []
        _BY_NAME = {}
        return

    wb = openpyxl.load_workbook(OPERATIONS_XLSX, read_only=True, data_only=True)
    ws = wb.active
    ops = []
    for row in ws.iter_rows(min_row=3, values_only=True):
        # Столбцы: №, Название, Описание, Применение, Ограничения
        if not row[0] or not row[1]:
            continue
        try:
            number = int(row[0])
        except (TypeError, ValueError):
            continue
        name = str(row[1]).strip()
        description = str(row[2]).strip() if row[2] else ""
        applicability = str(row[3]).strip() if row[3] else ""
        restrictions = str(row[4]).strip() if row[4] else ""
        ops.append(OperationInfo(number, name, description, applicability, restrictions))

    wb.close()
    _OPERATIONS = ops
    _BY_NAME = {op.name: op for op in ops}
    print(f"[INFO] Загружено операций: {len(ops)}", flush=True)


def get_all() -> list[OperationInfo]:
    if _OPERATIONS is None:
        _load()
    return _OPERATIONS


def get_by_name(name: str) -> Optional[OperationInfo]:
    if _BY_NAME is None:
        _load()
    return _BY_NAME.get(name)


def format_operations_for_prompt() -> str:
    """Форматирует список операций с условиями применения для промпта LLM."""
    ops = get_all()
    if not ops:
        return ""
    lines = ["СПРАВОЧНИК ОПЕРАЦИЙ (условия применения):"]
    for op in ops:
        line = f"- {op.name}"
        if op.applicability:
            line += f": {op.applicability}"
        if op.restrictions:
            line += f" | Ограничения: {op.restrictions}"
        lines.append(line)
    return "\n".join(lines)
