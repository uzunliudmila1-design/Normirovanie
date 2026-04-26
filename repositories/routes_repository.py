"""Репозиторий типовых маршрутов: загрузка из Excel, парсинг, фильтрация."""

from __future__ import annotations
import os
from typing import Optional

try:
    import openpyxl
    _OPENPYXL = True
except ImportError:
    _OPENPYXL = False

from config import TYPICAL_ROUTES_XLSX
from models.schemas import DrawingFacts, RouteCandidate


# ─── Кеш ──────────────────────────────────────────────────────────────────────

_ROUTES: list[tuple[str, list[str]]] | None = None  # [(route_id, [операции])]


def _load():
    global _ROUTES

    if not _OPENPYXL:
        _ROUTES = []
        return

    if not os.path.exists(TYPICAL_ROUTES_XLSX):
        print(f"[ПРЕДУПРЕЖДЕНИЕ] Типовые маршруты не найдены: {TYPICAL_ROUTES_XLSX}", flush=True)
        _ROUTES = []
        return

    wb = openpyxl.load_workbook(TYPICAL_ROUTES_XLSX, read_only=True, data_only=True)
    ws = wb.active
    routes = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        route_id = str(row[0]).strip() if row[0] else ""
        route_str = str(row[1]).strip() if row[1] else ""
        if route_id and route_str:
            operations = [op.strip() for op in route_str.split("|")]
            routes.append((route_id, operations))
    wb.close()
    _ROUTES = routes
    print(f"[INFO] Загружено типовых маршрутов: {len(routes)}", flush=True)


def get_all() -> list[tuple[str, list[str]]]:
    if _ROUTES is None:
        _load()
    return _ROUTES


# ─── Маппинг: признак из facts → какие операции он подразумевает ──────────────

_FACT_TO_OPERATIONS: dict[str, list[str]] = {
    "has_cutting": [
        "Газо-плазменная резка", "Газо-плазменная резка (ручная)",
        "Газо-плазменная резка (стандарт)", "Лазерная резка",
        "Ленточно-отрезная", "Отрезная",
        "Фаска (газо-плазменная резка)", "Фаска (фрезерование)",
    ],
    "has_bending": ["Гибка", "Вальцовка"],
    "has_welding": [
        "Сварка полуавтоматическая", "Сварка роботизированная",
        "Сварка автоматическая",
        "Прихватка",
        "Наплавка",
        "Пайка",
    ],
    "has_machining": [
        "Токарная", "Токарная с ЧПУ", "Фрезерная", "Фрезерная с ЧПУ",
        "Сверлильная", "Расточная", "Долбежная", "Зубонарезная",
        "Электроэрозионная",
    ],
    "has_grinding": [
        "Круглошлифовальная", "Плоскошлифовальная", "Внутришлифовальная",
    ],
    "has_painting": ["Покраска"],
    "has_heat_treatment": [
        "Термообработка", "Азотирование", "Закалка ТВЧ",
    ],
    "has_assembly": [
        "Сборка/Разборка",
        "Комплектовочная", "Комплектовочная (магазин)",
        "Комплектовочная (подготовка)", "Комплектовочная (покупные)",
    ],
    "has_cleaning": ["Очистка дробеметная", "Очистка пескоструйная"],
    "has_straightening": ["Рихтовка"],
    "has_holes": ["Слесарная", "Зачистка"],
}

# Обратный индекс: операция -> какой факт она подразумевает
_OPERATION_TO_FACT: dict[str, str] = {}
for fact, ops in _FACT_TO_OPERATIONS.items():
    for op in ops:
        _OPERATION_TO_FACT[op] = fact


def _score_route(route_ops: list[str], facts: DrawingFacts) -> tuple[float, list[str], list[str]]:
    """Оценивает релевантность маршрута по фактам из чертежа.

    Возвращает (score, match_reasons, mismatch_reasons).
    Score от 0 до 1.
    """
    match_reasons = []
    mismatch_reasons = []

    # Какие факты есть у чертежа
    active_facts = set()
    for fact_name in _FACT_TO_OPERATIONS:
        if getattr(facts, fact_name, False):
            active_facts.add(fact_name)

    # Какие факты покрывает маршрут
    route_facts = set()
    for op in route_ops:
        if op in _OPERATION_TO_FACT:
            route_facts.add(_OPERATION_TO_FACT[op])

    if not active_facts:
        # Нет данных — не можем оценить
        return 0.3, ["Недостаточно данных для оценки"], []

    # Совпадения: факты чертежа, которые маршрут покрывает
    matched = active_facts & route_facts
    for f in matched:
        match_reasons.append(f"Маршрут содержит операции для {f}")

    # Пропуски: факты чертежа, которые маршрут НЕ покрывает
    missed = active_facts - route_facts
    for f in missed:
        mismatch_reasons.append(f"Нет операций для {f}")

    # Лишнее: операции маршрута, для которых нет фактов
    extra_facts = route_facts - active_facts
    for f in extra_facts:
        mismatch_reasons.append(f"Лишние операции: {f}")

    # Формула оценки
    if not active_facts:
        score = 0.3
    else:
        coverage = len(matched) / len(active_facts)  # Покрытие фактов
        penalty = len(extra_facts) * 0.15  # Штраф за лишние операции
        score = max(0.0, min(1.0, coverage - penalty))

    return score, match_reasons, mismatch_reasons


def filter_routes(facts: DrawingFacts, min_score: float = 0.15, max_candidates: int = 15) -> list[RouteCandidate]:
    """Фильтрует маршруты по фактам из чертежа.

    Возвращает все маршруты с score >= min_score, но не более max_candidates.
    """
    all_routes = get_all()
    if not all_routes:
        return []

    candidates = []
    for route_id, operations in all_routes:
        score, matches, mismatches = _score_route(operations, facts)
        if score >= min_score:
            candidates.append(RouteCandidate(
                route_id=route_id,
                operations=operations,
                score=score,
                match_reasons=matches,
                mismatch_reasons=mismatches,
            ))

    # Сортировка: лучший score первый
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:max_candidates]


def format_candidates_for_prompt(candidates: list[RouteCandidate]) -> str:
    """Форматирует кандидатов для промпта LLM."""
    lines = []
    for i, c in enumerate(candidates, 1):
        ops_str = " | ".join(c.operations)
        lines.append(f"{i}. {c.route_id}: {ops_str}")
        if c.mismatch_reasons:
            lines.append(f"   Расхождения: {'; '.join(c.mismatch_reasons)}")
    return "\n".join(lines)


