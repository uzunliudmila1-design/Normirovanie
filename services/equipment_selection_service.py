"""Этап 4: подбор оборудования — фильтрация кодом + довыбор моделью."""

from models.schemas import DrawingFacts, EquipmentChoice, LLMCallMetrics
from repositories.equipment_repository import (
    filter_by_operation_and_workshop,
    format_shortlist,
)
from prompts.choose_equipment import build_choose_equipment_prompt
from services.claude_service import call_llm_text
from services.rules_service import load_rules

# Маппинг стандартных операций → операции из базы оборудования
# (в equipment.xlsx колонки «Операция 1/2/3» могут отличаться от названий в маршруте)
_OPERATION_ALIASES = {
    "Газо-плазменная резка": ["Газо-плазменная резка", "Газо-плазменная резка (стандарт)", "Газо-плазменная резка (ручная)"],
    "Газо-плазменная резка (стандарт)": ["Газо-плазменная резка", "Газо-плазменная резка (стандарт)"],
    "Газо-плазменная резка (ручная)": ["Газо-плазменная резка", "Газо-плазменная резка (ручная)"],
    "Токарная": ["Токарная", "Токарная с ЧПУ"],
    "Токарная с ЧПУ": ["Токарная с ЧПУ", "Токарная"],
    "Фрезерная": ["Фрезерная", "Фрезерная с ЧПУ"],
    "Фрезерная с ЧПУ": ["Фрезерная с ЧПУ", "Фрезерная"],
    "Сварка полуавтоматическая": ["Сварка полуавтоматическая", "Сварка роботизированная"],
    "Прихватка": ["Прихватка", "Сварка полуавтоматическая"],
    "Прихватка + Сварка полуавтоматическая": ["Сварка полуавтоматическая", "Прихватка"],
}

# Операции, не требующие оборудования
_NO_EQUIPMENT_OPS = {
    "Комплектовочная", "Комплектовочная (магазин)", "Комплектовочная (подготовка)",
    "Комплектовочная (покупные)", "Контрольная", "Контрольная ГП",
    "Маркировка", "Консервация",
}


def select_equipment(
    operations: list[str],
    facts: DrawingFacts,
) -> tuple[list[EquipmentChoice], list[LLMCallMetrics]]:
    """Подбирает оборудование для каждой операции.

    Шаг 1: код фильтрует по операции + цеху → shortlist
    Шаг 2: если shortlist > 1, модель выбирает лучший
    """
    workshop = facts.workshop or ""

    # Шаг 1: собираем shortlist по каждой операции
    ops_with_equipment = []
    auto_choices = []

    for op in operations:
        # Убираем номер операции (010, 015, 020...) для поиска
        op_name = _strip_op_number(op)

        if op_name in _NO_EQUIPMENT_OPS:
            auto_choices.append(EquipmentChoice(
                operation=op,
                equipment_name="—",
                workshop="",
                reasoning="Операция не требует оборудования",
            ))
            continue

        # Цех берём из маршрутной карты; если не найдено — ищем по всем цехам
        op_workshop = workshop

        # Ищем по основному имени и алиасам
        search_names = _OPERATION_ALIASES.get(op_name, [op_name])
        candidates = []
        for search_name in search_names:
            found = filter_by_operation_and_workshop(search_name, op_workshop)
            candidates.extend(found)

        # Дедупликация
        seen = set()
        unique = []
        for c in candidates:
            if c.name not in seen:
                seen.add(c.name)
                unique.append(c)

        if not unique:
            # Нет оборудования — будет выбрано моделью или останется "—"
            auto_choices.append(EquipmentChoice(
                operation=op,
                equipment_name="—",
                workshop="",
                reasoning=f"Оборудование для '{op_name}' не найдено в базе",
            ))
            print(f"[ЭТАП 4] {op}: оборудование не найдено в базе", flush=True)
            continue

        if len(unique) == 1:
            # Единственный вариант — автовыбор
            item = unique[0]
            ws_label = f"Цех №{item.workshop}" if item.workshop.isdigit() else item.workshop
            auto_choices.append(EquipmentChoice(
                operation=op,
                equipment_name=f"{item.name} [{ws_label}]",
                workshop=item.workshop,
                reasoning="Единственный подходящий вариант в базе",
            ))
            print(f"[ЭТАП 4] {op}: автовыбор {item.name[:40]}", flush=True)
            continue

        # Несколько вариантов — нужен довыбор
        shortlist_text = format_shortlist(unique, max_items=len(unique))
        ops_with_equipment.append((op, op_name, shortlist_text, unique))

    # Шаг 2: для операций с несколькими вариантами — вызов модели
    llm_metrics = []
    if ops_with_equipment:
        llm_choices, llm_metrics = _select_via_llm(ops_with_equipment, facts)
        auto_choices.extend(llm_choices)

    # Сортируем по порядку операций
    op_order = {op: i for i, op in enumerate(operations)}
    auto_choices.sort(key=lambda c: op_order.get(c.operation, 999))

    return auto_choices, llm_metrics


def _select_via_llm(
    ops_with_equipment: list[tuple],
    facts: DrawingFacts,
) -> tuple[list[EquipmentChoice], list[LLMCallMetrics]]:
    """Вызывает модель для выбора из shortlist по нескольким операциям за один вызов."""
    rules_text = load_rules()
    if rules_text:
        print(f"[ЭТАП 4] Загружены бизнес-правила ({len(rules_text)} символов)", flush=True)

    lines = [f"Part: {facts.detail_name}, material: {facts.material}"]
    if facts.min_roughness_ra:
        lines.append(f"Surface: Ra {facts.min_roughness_ra}")
    if facts.min_tolerance_it:
        lines.append(f"Tolerance: IT{facts.min_tolerance_it}")
    lines.append("")

    for op, op_name, shortlist_text, _ in ops_with_equipment:
        lines.append(f"Operation: {op}")
        lines.append(f"Available equipment:\n{shortlist_text}")
        lines.append("")

    user_prompt = (
        "\n".join(lines)
        + "\nSelect the best equipment for EACH operation. "
        "Return JSON array with EXACTLY these keys per element: "
        '"operation" (copy EXACTLY as shown above), "equipment_name", "workshop", "reasoning". '
        "JSON array ONLY."
    )

    try:
        raw, llm_metrics = call_llm_text(
            system_prompt=build_choose_equipment_prompt(rules_text),
            user_prompt=user_prompt,
        )

        if not isinstance(raw, list):
            raw = [raw]

        # Маппинг: имя операции без номера -> полное имя с номером
        op_name_to_full = {}
        for op, op_name, _, _ in ops_with_equipment:
            op_name_to_full[op_name.lower()] = op
            op_name_to_full[op.lower()] = op

        choices = []
        for item in raw:
            raw_op = item.get("operation", "")
            # Сопоставить с реальным именем операции
            matched_op = op_name_to_full.get(raw_op.lower(), "")
            if not matched_op:
                # Попробовать частичное совпадение
                for key, full_op in op_name_to_full.items():
                    if key in raw_op.lower() or raw_op.lower() in key:
                        matched_op = full_op
                        break
            choices.append(EquipmentChoice(
                operation=matched_op or raw_op,
                equipment_name=item.get("equipment_name", "—"),
                workshop=str(item.get("workshop", "")),
                reasoning=item.get("reasoning", ""),
            ))
            print(f"[ЭТАП 4] {matched_op or raw_op}: модель выбрала {item.get('equipment_name', '?')[:40]}", flush=True)
        return choices, llm_metrics

    except Exception as e:
        print(f"[ЭТАП 4] Ошибка LLM при выборе оборудования: {e}", flush=True)
        # Fallback: берём первый из списка
        fallback = []
        for op, op_name, _, candidates in ops_with_equipment:
            item = candidates[0]
            ws_label = f"Цех №{item.workshop}" if item.workshop.isdigit() else item.workshop
            fallback.append(EquipmentChoice(
                operation=op,
                equipment_name=f"{item.name} [{ws_label}]",
                workshop=item.workshop,
                reasoning=f"Автовыбор (LLM недоступна): первый из списка",
            ))
        return fallback, []


def _strip_op_number(op: str) -> str:
    """Убирает номер операции: '010 Токарная' -> 'Токарная'."""
    parts = op.strip().split(None, 1)
    if len(parts) == 2 and parts[0].isdigit():
        return parts[1]
    return op.strip()
