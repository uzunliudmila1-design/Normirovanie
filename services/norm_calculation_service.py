"""Этап 5: расчёт норм времени.

Стратегия: модель считает нормы, но получает только конкретную информацию
по каждой операции (оборудование уже выбрано, маршрут уже определён).
Промпт короткий и узкий — не нужно выбирать маршрут/оборудование.
"""

from models.schemas import DrawingFacts, EquipmentChoice, OperationNorm, LLMCallMetrics
from prompts.calculate_norms import CALCULATE_NORMS_PROMPT
from services.claude_service import call_llm_with_pdf


def calculate_norms(
    operations: list[str],
    equipment_choices: list[EquipmentChoice],
    facts: DrawingFacts,
    chertezh_file,
    marshrutnaya_file=None,
    batch_size: int = 1,
) -> tuple[list[OperationNorm], list[LLMCallMetrics]]:
    """Расчёт норм: модель получает конкретные операции + оборудование + чертёж.

    Промпт короткий — только расчёт, без выбора маршрута/оборудования.
    """
    # Строим контекст: какая операция — какое оборудование
    eq_map = {c.operation: c for c in equipment_choices}

    ops_text_lines = []
    for op in operations:
        eq = eq_map.get(op)
        eq_name = eq.equipment_name if eq else "—"
        ops_text_lines.append(f"- {op} → оборудование: {eq_name}")

    ops_text = "\n".join(ops_text_lines)

    facts_text = (
        f"Деталь: {facts.detail_name}\n"
        f"Материал: {facts.material}\n"
    )
    if facts.mass_kg:
        facts_text += f"Масса: {facts.mass_kg} кг\n"
    dims = []
    if facts.length_mm:
        dims.append(f"L={facts.length_mm}")
    if facts.width_mm:
        dims.append(f"W={facts.width_mm}")
    if facts.height_mm:
        dims.append(f"H={facts.height_mm}")
    if facts.diameter_mm:
        dims.append(f"D={facts.diameter_mm}")
    if dims:
        facts_text += f"Габариты (мм): {', '.join(dims)}\n"
    if facts.min_tolerance_it:
        facts_text += f"Точность: IT{facts.min_tolerance_it}\n"
    if facts.min_roughness_ra:
        facts_text += f"Шероховатость: Ra {facts.min_roughness_ra}\n"

    user_prompt = (
        f"PART DATA:\n{facts_text}\n"
        f"OPERATIONS AND EQUIPMENT:\n{ops_text}\n\n"
        f"Batch size: {batch_size} parts.\n\n"
        f"Calculate t_шт and t_пз for EACH operation. Return a JSON array where "
        f"each element has EXACTLY these keys: \"операция\", \"t_шт_предложено\", "
        f"\"t_пз_предложено\", \"режимы\", \"обоснование\". "
        f"JSON array ONLY. No other keys. No nested objects."
    )

    # Отправляем чертёж для визуального анализа размеров
    pdf_files = [("Чертёж детали", chertezh_file)]
    if marshrutnaya_file:
        pdf_files.append(("Маршрутная карта", marshrutnaya_file))

    raw, llm_metrics = call_llm_with_pdf(
        system_prompt=CALCULATE_NORMS_PROMPT,
        user_prompt=user_prompt,
        pdf_files=pdf_files,
    )

    if not isinstance(raw, list):
        raw = [raw]

    # Собираем результат, обогащаем оборудованием
    norms = []
    for item in raw:
        op_name = item.get("операция", "")
        eq = eq_map.get(op_name)

        norm = OperationNorm(
            **{
                "деталь": facts.detail_name,
                "операция": op_name,
                "оборудование": eq.equipment_name if eq else "—",
                "t_шт_предложено": float(item.get("t_шт_предложено", 0)),
                "t_пз_предложено": float(item.get("t_пз_предложено", 0)),
                "режимы": item.get("режимы", "—"),
                "обоснование": item.get("обоснование", ""),
            }
        )
        norms.append(norm)
        print(
            f"[ЭТАП 5] {op_name}: t_шт={norm.t_sht}, t_пз={norm.t_pz}, режимы={norm.modes[:40]}",
            flush=True,
        )

    return norms, llm_metrics
