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

    # 4. Проверка: покрасочное оборудование из Цех №3
    for eq in equipment_choices:
        op_lower = eq.operation.lower()
        if any(kw in op_lower for kw in ("покраска", "грунт", "окраска", "лак")):
            ws = eq.workshop.strip()
            if ws and ws != "3" and ws != "Цех №3":
                warnings.append(
                    f"ПРЕДУПРЕЖДЕНИЕ: {eq.operation} — оборудование из Цех №{ws}, "
                    f"но покрасочные камеры только в Цех №3"
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
    """Операции, не требующие оборудования/режимов."""
    manual = {
        "комплектовочная", "контрольная", "контрольная гп", "маркировка",
        "консервация", "испытание", "рихтовка",
    }
    # Убираем номер
    parts = op_name.strip().split(None, 1)
    name = parts[1].lower() if len(parts) == 2 and parts[0].isdigit() else op_name.lower()
    return name in manual
