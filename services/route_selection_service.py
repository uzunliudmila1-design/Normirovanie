"""Этапы 2-3: фильтрация маршрутов кодом + выбор моделью из shortlist."""

import hashlib
import json

from models.schemas import DrawingFacts, SelectedRoute, RouteCandidate, LLMCallMetrics
from repositories.routes_repository import filter_routes, format_candidates_for_prompt
from repositories.operations_repository import format_operations_for_prompt
from prompts.choose_route import build_choose_route_prompt
from services.claude_service import call_llm_text
from services.cache_service import make_key, get as cache_get, put as cache_put
from services.rules_service import load_rules


def select_route(facts: DrawingFacts) -> tuple[SelectedRoute, list[LLMCallMetrics]]:
    """Двухэтапный выбор маршрута: код фильтрует → модель выбирает из shortlist."""

    # ── Этап 2: фильтрация кодом ──
    candidates = filter_routes(facts)

    if not candidates:
        print("[ЭТАП 2] Нет подходящих маршрутов в каталоге", flush=True)
        return SelectedRoute(
            route_id="—",
            operations=[],
            source="не найден",
            confidence=0,
            reasoning="В каталоге типовых маршрутов не найдено подходящих вариантов",
        ), []

    print(f"[ЭТАП 2] Отфильтровано {len(candidates)} кандидатов: "
          f"{', '.join(c.route_id for c in candidates)}", flush=True)

    # Если единственный кандидат — автовыбор (нечего выбирать)
    if len(candidates) == 1:
        best = candidates[0]
        print(f"[ЭТАП 3] Единственный кандидат: {best.route_id} (score={best.score:.2f})", flush=True)
        return SelectedRoute(
            route_id=best.route_id,
            operations=best.operations,
            source="типовой каталог",
            confidence=int(best.score * 100),
            reasoning=f"Единственный подходящий маршрут: {'; '.join(best.match_reasons)}",
            alternatives=[],
        ), []  # без LLM

    # ── Этап 3: модель выбирает из shortlist ──
    # Кэш по хэшу facts + кандидатов
    facts_hash = hashlib.sha256(facts.model_dump_json().encode()).hexdigest()[:16]
    cand_hash = hashlib.sha256("|".join(c.route_id for c in candidates).encode()).hexdigest()[:16]
    cache_key = make_key("route", facts_hash, cand_hash)

    cached = cache_get(cache_key)
    if cached and cached.get("route_id"):
        chosen_id = cached.get("route_id", "")
        chosen = next((c for c in candidates if c.route_id == chosen_id), candidates[0])
        raw_conf = cached.get("confidence", 50)
        try:
            conf = int(raw_conf)
        except (ValueError, TypeError):
            conf = {"low": 25, "medium": 50, "high": 85}.get(str(raw_conf).lower(), 50)
        print(f"[ЭТАП 3] Маршрут из кэша: {chosen.route_id}", flush=True)
        suggested: list[str] = []
        if conf < 60:
            suggested = _suggest_route_from_facts(facts)
            print(f"[ЭТАП 3] Уверенность низкая ({conf}%) — предложен маршрут (кэш): {' | '.join(suggested)}", flush=True)
        return SelectedRoute(
            route_id=chosen.route_id,
            operations=chosen.operations,
            source="типовой каталог",
            confidence=conf,
            reasoning=cached.get("reasoning", ""),
            alternatives=[c.route_id for c in candidates if c.route_id != chosen.route_id],
            suggested_route=suggested,
        ), []  # из кэша

    candidates_text = format_candidates_for_prompt(candidates)
    facts_text = _format_facts_for_prompt(facts)

    rules_text = load_rules()
    if rules_text:
        print(f"[ЭТАП 3] Загружены бизнес-правила ({len(rules_text)} символов)", flush=True)

    operations_text = format_operations_for_prompt()

    user_prompt = (
        f"PART FACTS:\n{facts_text}\n\n"
        f"CANDIDATE ROUTES:\n{candidates_text}\n\n"
        f"Select ONE route. Return JSON with EXACTLY these keys: "
        f'"route_id" (e.g. "M-0026"), "confidence" (integer 0-100), '
        f'"reasoning" (in Russian). JSON ONLY.'
    )

    raw, llm_metrics = call_llm_text(
        system_prompt=build_choose_route_prompt(rules_text, operations_text),
        user_prompt=user_prompt,
    )

    chosen_id = raw.get("route_id", "") or ""
    raw_conf = raw.get("confidence", 50)
    try:
        confidence = int(raw_conf)
    except (ValueError, TypeError):
        # Модель вернула "low"/"medium"/"high" вместо числа
        confidence = {"low": 25, "medium": 50, "high": 85}.get(str(raw_conf).lower(), 50)
    reasoning = raw.get("reasoning", "")

    # Найти выбранный маршрут в кандидатах
    chosen = next((c for c in candidates if c.route_id == chosen_id), None)
    if not chosen:
        # Модель вернула route_id которого нет в кандидатах — берём лучший
        chosen = candidates[0]
        print(f"[ЭТАП 3] route_id '{chosen_id}' не найден, fallback: {chosen.route_id}", flush=True)

    # Кэшируем только валидный ответ
    cache_put(cache_key, "route", {
        "route_id": chosen.route_id,
        "confidence": confidence,
        "reasoning": reasoning,
    })

    print(f"[ЭТАП 3] Модель выбрала: {chosen.route_id} (confidence={confidence})", flush=True)

    suggested: list[str] = []
    if confidence < 60:
        suggested = _suggest_route_from_facts(facts)
        print(f"[ЭТАП 3] Уверенность низкая ({confidence}%) — предложен маршрут: {' | '.join(suggested)}", flush=True)

    return SelectedRoute(
        route_id=chosen.route_id,
        operations=chosen.operations,
        source="типовой каталог",
        confidence=confidence,
        reasoning=reasoning,
        alternatives=[c.route_id for c in candidates if c.route_id != chosen.route_id],
        suggested_route=suggested,
    ), llm_metrics


def _format_facts_for_prompt(facts: DrawingFacts) -> str:
    lines = [
        f"Тип детали: {facts.detail_type}",
        f"Название: {facts.detail_name}",
        f"Материал: {facts.material}",
    ]
    if facts.mass_kg:
        lines.append(f"Масса: {facts.mass_kg} кг")
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
        lines.append(f"Габариты (мм): {', '.join(dims)}")

    flags = []
    for attr, label in [
        ("has_cutting", "резка"), ("has_bending", "гибка"),
        ("has_welding", "сварка"), ("has_machining", "мехобработка"),
        ("has_grinding", "шлифование"), ("has_painting", "покраска"),
        ("has_heat_treatment", "термообработка"), ("has_assembly", "сборка"),
        ("has_cleaning", "очистка"), ("has_straightening", "рихтовка"),
        ("has_holes", "отверстия"), ("has_threading", "резьба"),
        ("has_slots", "пазы"),
    ]:
        if getattr(facts, attr, False):
            flags.append(label)
    if flags:
        lines.append(f"Признаки: {', '.join(flags)}")

    if facts.min_tolerance_it:
        lines.append(f"Точность: IT{facts.min_tolerance_it}")
    if facts.min_roughness_ra:
        lines.append(f"Шероховатость: Ra {facts.min_roughness_ra}")

    return "\n".join(lines)


def _suggest_route_from_facts(facts: DrawingFacts) -> list[str]:
    """Строит рекомендуемый маршрут на основе фактов чертежа и бизнес-правил.

    Используется когда уверенность выбранного маршрута < 60%.
    Порядок операций — технологическая последовательность.
    """
    ops: list[str] = []

    # 1. Сборочный чертёж: первая операция — Комплектовочная
    if facts.is_assembly:
        ops.append("Комплектовочная")

    # 2. Резка (бизнес-правило: толщина ≤ 12 мм → лазер, > 12 мм → плазма/газ)
    if facts.has_cutting:
        thickness = facts.thickness_mm or facts.height_mm or facts.width_mm
        if thickness and thickness <= 12:
            ops.append("Лазерная резка")
        else:
            ops.append("Газо-плазменная резка")
            ops.append("Зачистка")  # после газо-плазменной резки всегда идёт зачистка

    # 3. Гибка / вальцовка
    if facts.has_bending:
        ops.append("Гибка")

    # 4. Сварка (прихватка → сварка)
    if facts.has_welding:
        ops.append("Прихватка")
        ops.append("Сварка полуавтоматическая")

    # 5. Мехобработка
    if facts.has_machining:
        # Тела вращения (вал, втулка) → токарная; остальные → фрезерная
        if facts.detail_type and any(k in facts.detail_type.lower() for k in ("вал", "втулк", "ось", "шток")):
            ops.append("Токарная")
        else:
            ops.append("Фрезерная")

    # 6. Шлифование
    if facts.has_grinding:
        ops.append("Шлифовальная")

    # 7. Термообработка
    if facts.has_heat_treatment:
        ops.append("Термообработка")

    # 8. Очистка (всегда после сварки — бизнес-правило)
    if facts.has_cleaning:
        ops.append("Очистка дробеметная")

    # 9. Слесарная (отверстия, пазы, резьба)
    if facts.has_holes or facts.has_threading or facts.has_slots:
        ops.append("Слесарная")

    # 10. Рихтовка (только при толщине ≥ 10 мм — бизнес-правило)
    if facts.has_straightening:
        thickness = facts.thickness_mm or facts.height_mm or facts.width_mm
        if thickness is None or thickness >= 10:  # запрещена для деталей < 10 мм
            ops.append("Рихтовка")

    # 11. Покраска
    if facts.has_painting:
        ops.append("Покраска")

    # 12. Зачистка — если есть сварка
    if facts.has_welding and "Зачистка" not in ops:
        # вставляем зачистку после последней сварочной операции
        try:
            last_weld = max(i for i, o in enumerate(ops) if "варк" in o.lower() or "прихватк" in o.lower())
            ops.insert(last_weld + 1, "Зачистка")
        except ValueError:
            pass

    # 13. Маркировка — всегда перед концом
    ops.append("Маркировка")

    # 14. Сборочный чертёж: последняя — Контрольная ГП
    if facts.is_assembly:
        ops.append("Контрольная ГП")

    return ops
