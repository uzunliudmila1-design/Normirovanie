"""Репозиторий оборудования: загрузка из Excel, нормализация, фильтрация."""

from __future__ import annotations
import os
from typing import Optional

try:
    import openpyxl
    _OPENPYXL = True
except ImportError:
    _OPENPYXL = False

from config import EQUIPMENT_XLSX
from models.schemas import EquipmentItem


# ─── Нормализованный кеш ──────────────────────────────────────────────────────

_EQUIPMENT: list[EquipmentItem] | None = None
_BY_OPERATION: dict[str, list[EquipmentItem]] | None = None


def _normalize_workshop(raw) -> str:
    """Приводит цех к единому формату: '1', '2', '3', '4', 'ДорИнвест' или ''."""
    if raw is None:
        return ""
    s = str(raw).strip()
    # Числовые значения из Excel
    if s in ("1", "1.0", "2", "2.0", "3", "3.0", "4", "4.0"):
        return s.split(".")[0]
    if "ДорИнвест" in s or "Дор" in s:
        return "ДорИнвест"
    if "Цех" in s:
        # "Цех №1" -> "1"
        for ch in s:
            if ch.isdigit():
                return ch
    return s


def _load():
    """Загружает оборудование из Excel, нормализует, индексирует по операциям."""
    global _EQUIPMENT, _BY_OPERATION

    if not _OPENPYXL:
        print("[ПРЕДУПРЕЖДЕНИЕ] openpyxl не установлен — база оборудования недоступна", flush=True)
        _EQUIPMENT = []
        _BY_OPERATION = {}
        return

    if not os.path.exists(EQUIPMENT_XLSX):
        print(f"[ПРЕДУПРЕЖДЕНИЕ] Файл оборудования не найден: {EQUIPMENT_XLSX}", flush=True)
        _EQUIPMENT = []
        _BY_OPERATION = {}
        return

    wb = openpyxl.load_workbook(EQUIPMENT_XLSX, read_only=True, data_only=True)
    ws = wb["Лист1"]

    items = []
    for row in ws.iter_rows(min_row=3, values_only=True):
        if not row[1]:
            continue
        name = str(row[1]).replace("\xa0", " ").strip()
        workshop = _normalize_workshop(row[2])
        department = str(row[3]).strip() if row[3] else ""
        ops = [str(x).strip() for x in [row[4], row[5], row[6]] if x]

        items.append(EquipmentItem(
            name=name,
            workshop=workshop,
            department=department,
            operations=ops,
        ))
    wb.close()

    _EQUIPMENT = items

    # Индекс: операция -> список оборудования
    by_op: dict[str, list[EquipmentItem]] = {}
    for item in items:
        for op in item.operations:
            by_op.setdefault(op, []).append(item)
    _BY_OPERATION = by_op

    print(f"[INFO] Загружено оборудования: {len(items)}, операций: {len(by_op)}", flush=True)


def filter_by_operation(operation: str) -> list[EquipmentItem]:
    """Возвращает оборудование, подходящее для данной операции."""
    if _BY_OPERATION is None:
        _load()
    return _BY_OPERATION.get(operation, [])


def filter_by_operation_and_workshop(
    operation: str,
    preferred_workshop: Optional[str] = None,
) -> list[EquipmentItem]:
    """Фильтрует оборудование по операции, приоритет — цех.

    Возвращает (в порядке приоритета):
    1. Оборудование из preferred_workshop
    2. Если нет → всё доступное по операции
    """
    candidates = filter_by_operation(operation)
    if not candidates:
        return []

    if preferred_workshop:
        in_workshop = [e for e in candidates if e.workshop == preferred_workshop]
        if in_workshop:
            return in_workshop

    return candidates


def format_shortlist(items: list[EquipmentItem], max_items: int = 10) -> str:
    """Форматирует краткий список оборудования для промпта LLM."""
    seen = set()
    lines = []
    for item in items:
        key = item.name[:50]
        if key in seen:
            continue
        seen.add(key)
        workshop_str = f" [Цех №{item.workshop}]" if item.workshop.isdigit() else f" [{item.workshop}]" if item.workshop else ""
        lines.append(f"  • {item.name[:80]}{workshop_str}")
        if len(lines) >= max_items:
            break
    return "\n".join(lines)


