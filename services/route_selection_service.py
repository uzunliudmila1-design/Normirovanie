"""Этапы 2-3: фильтрация маршрутов кодом + выбор моделью из shortlist."""

import hashlib
import json

from models.schemas import DrawingFacts, SelectedRoute, RouteCandidate, LLMCallMetrics
from repositories.routes_repository import filter_routes, format_candidates_for_prompt
from prompts.choose_route import CHOOSE_ROUTE_PROMPT
from services.claude_service import call_llm_text
from services.cache_service import make_key, get as cache_get, put as cache_put


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

    # Если лучший кандидат с большим отрывом — можно обойтись без модели
    if len(candidates) == 1 or (candidates[0].score > 0.8 and candidates[0].score - candidates[1].score > 0.3):
        best = candidates[0]
        print(f"[ЭТАП 3] Однозначный выбор кодом: {best.route_id} (score={best.score:.2f})", flush=True)
        return SelectedRoute(
            route_id=best.route_id,
            operations=best.operations,
            source="типовой каталог",
            confidence=int(best.score * 100),
            reasoning=f"Автовыбор: {'; '.join(best.match_reasons)}",
            alternatives=[c.route_id for c in candidates[1:]],
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
        return SelectedRoute(
            route_id=chosen.route_id,
            operations=chosen.operations,
            source="типовой каталог",
            confidence=conf,
            reasoning=cached.get("reasoning", ""),
            alternatives=[c.route_id for c in candidates if c.route_id != chosen.route_id],
        ), []  # из кэша

    candidates_text = format_candidates_for_prompt(candidates)
    facts_text = _format_facts_for_prompt(facts)

    user_prompt = (
        f"PART FACTS:\n{facts_text}\n\n"
        f"CANDIDATE ROUTES:\n{candidates_text}\n\n"
        f"Select ONE route. Return JSON with EXACTLY these keys: "
        f'"route_id" (e.g. "M-0026"), "confidence" (integer 0-100), '
        f'"reasoning" (in Russian). JSON ONLY.'
    )

    raw, llm_metrics = call_llm_text(
        system_prompt=CHOOSE_ROUTE_PROMPT,
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

    return SelectedRoute(
        route_id=chosen.route_id,
        operations=chosen.operations,
        source="типовой каталог",
        confidence=confidence,
        reasoning=reasoning,
        alternatives=[c.route_id for c in candidates if c.route_id != chosen.route_id],
    ), llm_metrics


def route_from_mk(operations_list: list[str]) -> SelectedRoute:
    """Для Режима А: маршрут уже задан маршрутной картой."""
    return SelectedRoute(
        route_id="—",
        operations=operations_list,
        source="маршрутная карта",
        confidence=100,
        reasoning="Маршрут взят из предоставленной маршрутной карты",
    )


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
