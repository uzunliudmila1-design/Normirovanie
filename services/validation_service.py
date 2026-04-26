"""Этап 6: жёсткая валидация финального результата."""

from models.schemas import DrawingFacts, SelectedRoute, OperationNorm, EquipmentChoice


def validate_result(
    facts: DrawingFacts,
    route: SelectedRoute,
    equipment_choices: list[EquipmentChoice],
    norms: list[OperationNorm],
) -> list[str]:
    """Проверяет итоговый результат на логические противоречия.

    Возвращает список предупреждений/ошибок.
    """
    warnings = []

    # 1. Пустой результат
    if not norms:
        warnings.append("ОШИБКА: Нет ни одной рассчитанной операции")
        return warnings

    if not route.operations:
        warnings.append("ОШИБКА: Маршрут пуст")

    # 2. Проверка полей каждой операции
    for norm in norms:
        if not norm.operation:
            warnings.append("ОШИБКА: Операция без названия")
        if norm.t_sht <= 0:
            warnings.append(f"ПРЕДУПРЕЖДЕНИЕ: {norm.operation} — t_шт = {norm.t_sht} ≤ 0")
        if norm.t_pz < 0:
            warnings.append(f"ОШИБКА: {norm.operation} — t_пз = {norm.t_pz} < 0")
        if norm.t_sht > 480:  # > 8 часов на одну операцию — подозрительно
            warnings.append(f"ПРЕДУПРЕЖДЕНИЕ: {norm.operation} — t_шт = {norm.t_sht} мин (> 8 часов, подозрительно)")
        if norm.t_pz > 120:  # > 2 часов подготовки — подозрительно
            warnings.append(f"ПРЕДУПРЕЖДЕНИЕ: {norm.operation} — t_пз = {norm.t_pz} мин (> 2 часов, подозрительно)")

    # 3. Логические противоречия: facts vs маршрут
    route_ops_lower = " ".join(route.operations).lower()

    if facts.has_welding and "сварк" not in route_ops_lower and "прихват" not in route_ops_lower:
        warnings.append(
            "ПРОТИВОРЕЧИЕ: Чертёж показывает сварку, но в маршруте нет сварочных операций"
        )

    if facts.has_painting and "покраска" not in route_ops_lower and "грунт" not in route_ops_lower:
        warnings.append(
            "ПРОТИВОРЕЧИЕ: Чертёж показывает покраску, но в маршруте нет покрасочных операций"
        )

    if facts.has_machining and not any(
        kw in route_ops_lower for kw in ("токар", "фрезер", "сверл", "расточ", "шлиф", "долбеж")
    ):
        warnings.append(
            "ПРОТИВОРЕЧИЕ: Чертёж показывает мехобработку, но в маршруте нет станочных операций"
        )

    if facts.has_bending and "гибк" not in route_ops_lower and "вальц" not in route_ops_lower:
        warnings.append(
            "ПРОТИВОРЕЧИЕ: Чертёж показывает гибку, но в маршруте нет операции гибки"
        )

    # вспомогательная функция — имя операции без номера, в нижнем регистре
    def _op_bare(norm) -> str:
        parts = norm.operation.strip().split(None, 1)
        return (parts[1] if len(parts) == 2 and parts[0].isdigit() else norm.operation).lower()

    # 3а. Правило 1б: Фрезерная/Сверлильная не нужна для листовых деталей с резкой
    _SHEET_KW = ("листов", "ребро", "щека", "фланец", "пластин", "профил", "косынк", "заглушк")
    dt = (facts.detail_type or "").lower()
    dn = (facts.detail_name or "").lower()
    is_sheet = any(k in dt or k in dn for k in _SHEET_KW)
    route_has_cutting = any("плазм" in o.lower() or "лазерн" in o.lower() for o in route.operations)
    if is_sheet and route_has_cutting and facts.has_holes:
        for norm in norms:
            op = _op_bare(norm)
            if "фрезерн" in op or "сверлильн" in op:
                warnings.append(
                    f"ПРАВИЛО 1: {norm.operation} — у листовой детали с плазменной/лазерной резкой "
                    f"отверстия вырезаются резкой, операция не нужна"
                )

    # 3б. Правило 2: метод резки должен соответствовать толщине металла (≤12мм → лазер, >12мм → плазма)
    thickness = facts.thickness_mm or facts.height_mm or facts.width_mm
    if thickness is not None and facts.has_cutting:
        for norm in norms:
            op = _op_bare(norm)
            if "лазерн" in op and thickness > 12:
                warnings.append(
                    f"ПРАВИЛО 2: {norm.operation} — лазерная резка применяется при толщине ≤ 12 мм, "
                    f"а толщина детали {thickness} мм. Следует использовать газо-плазменную резку."
                )
            if ("плазм" in op) and thickness <= 12:
                warnings.append(
                    f"ПРАВИЛО 2: {norm.operation} — газо-плазменная резка применяется при толщине > 12 мм, "
                    f"а толщина детали {thickness} мм. Следует использовать лазерную резку."
                )

    # 3в. Шаг 2: Прихватка без Сварки — ошибка маршрута
    has_prikhvatka = any("прихватк" in _op_bare(n) for n in norms)
    has_svarka = any("сварк" in _op_bare(n) for n in norms)
    if has_prikhvatka and not has_svarka:
        warnings.append(
            "ПРАВИЛО 3: В маршруте есть 'Прихватка', но нет сварочной операции — "
            "прихватка выполняется только перед сваркой"
        )

    # 3г. Шаг 3: после сварки должна быть Зачистка
    weld_ops_idx = [i for i, n in enumerate(norms) if "сварк" in _op_bare(n)]
    zachistka_idx = [i for i, n in enumerate(norms) if "зачистк" in _op_bare(n)]
    if weld_ops_idx:
        last_weld_i = max(weld_ops_idx)
        zachistka_after_weld = any(z > last_weld_i for z in zachistka_idx)
        if not zachistka_after_weld:
            warnings.append(
                "ПРАВИЛО 4: В маршруте есть сварка, но после неё нет операции 'Зачистка' — "
                "зачистка сварных швов обязательна"
            )

    # 4. Порядок: очистка дробеметная/пескоструйная — после сварки
    clean_positions = [i for i, n in enumerate(norms) if "дробемет" in _op_bare(n) or "пескоструй" in _op_bare(n)]
    weld_positions  = [i for i, n in enumerate(norms) if "сварк" in _op_bare(n) or "прихватк" in _op_bare(n)]
    if clean_positions and weld_positions:
        last_weld = max(weld_positions)
        for ci in clean_positions:
            if ci < last_weld:
                warnings.append(
                    f"ПОРЯДОК: '{norms[ci].operation}' стоит перед сваркой — "
                    "очистка дробеметная выполняется только после сварки"
                )

    # 5. Оборудование задано
    ops_without_eq = [
        n.operation for n in norms
        if n.equipment == "—" and not _is_manual_operation(n.operation)
    ]
    if ops_without_eq:
        warnings.append(
            f"ПРЕДУПРЕЖДЕНИЕ: Нет оборудования для: {', '.join(ops_without_eq)}"
        )

    # 6. Режимы заданы для станочных операций
    for norm in norms:
        if not _is_manual_operation(norm.operation) and norm.modes in ("—", "", None):
            warnings.append(
                f"ПРЕДУПРЕЖДЕНИЕ: {norm.operation} — не указаны режимы обработки"
            )

    return warnings


def _is_manual_operation(op_name: str) -> bool:
    """Операции, не требующие отдельного оборудования и режимов обработки."""
    manual = {
        "комплектовочная", "комплектовочная (магазин)",
        "комплектовочная (подготовка)", "комплектовочная (покупные)",
        "контрольная", "контрольная гп",
        "маркировка", "консервация", "упаковка",
    }
    # Убираем номер
    parts = op_name.strip().split(None, 1)
    name = parts[1].lower() if len(parts) == 2 and parts[0].isdigit() else op_name.lower()
    return name in manual
