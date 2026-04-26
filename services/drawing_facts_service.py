"""Этап 1: извлечение фактов из чертежа.

Модель ТОЛЬКО извлекает факты, НЕ выбирает маршрут/оборудование.
Результат кэшируется по хэшу PDF — повторный запрос с тем же файлом не вызывает LLM.
"""

from models.schemas import DrawingFacts, LLMCallMetrics
from prompts.extract_facts import EXTRACT_FACTS_PROMPT
from services.claude_service import call_llm_with_pdf
from services.cache_service import file_hash, make_key, get as cache_get, put as cache_put


def extract_facts(chertezh_file) -> tuple[DrawingFacts, list[LLMCallMetrics]]:
    """Извлекает структурированные факты из чертежа.

    Возвращает DrawingFacts — Pydantic-модель.
    """
    # Проверяем кэш
    h1 = file_hash(chertezh_file)
    cache_key = make_key("facts", h1)

    cached = cache_get(cache_key)
    if cached:
        facts = DrawingFacts(**cached)
        print(f"[ЭТАП 1] Факты из кэша: тип={facts.detail_type}, confidence={facts.confidence}", flush=True)
        return facts, []  # из кэша — без LLM-метрик

    # Вызов LLM
    pdf_files = [("Чертёж детали", chertezh_file)]

    user_prompt = (
        "Extract facts from the document above. Return STRICTLY the JSON object "
        "with EXACTLY these keys: detail_type, detail_name, material, mass_kg, "
        "length_mm, width_mm, height_mm, diameter_mm, "
        "has_cutting, has_bending, has_welding, has_machining, has_grinding, "
        "has_painting, has_heat_treatment, has_assembly, has_cleaning, "
        "has_straightening, has_holes, has_threading, has_slots, "
        "min_tolerance_it, min_roughness_ra, has_geometric_tolerances, "
        "workshop, confidence, confidence_notes. "
        "JSON ONLY. No other keys. No nested objects."
    )

    raw, llm_metrics = call_llm_with_pdf(
        system_prompt=EXTRACT_FACTS_PROMPT,
        user_prompt=user_prompt,
        pdf_files=pdf_files,
    )

    # Нормализация ответа LLM: null→default, 0.85→85
    _BOOL_FIELDS = [
        "has_cutting", "has_bending", "has_welding", "has_machining",
        "has_grinding", "has_painting", "has_heat_treatment", "has_assembly",
        "has_cleaning", "has_straightening", "has_holes", "has_threading",
        "has_slots", "has_geometric_tolerances",
    ]
    for key in _BOOL_FIELDS:
        if key in raw and raw[key] is None:
            raw[key] = False

    for key in ("material", "detail_type", "detail_name", "confidence_notes"):
        if key in raw and raw[key] is None:
            raw[key] = ""

    if "confidence" in raw:
        c = raw["confidence"]
        if isinstance(c, float) and c <= 1.0:
            raw["confidence"] = int(c * 100)
        else:
            try:
                raw["confidence"] = int(c)
            except (ValueError, TypeError):
                raw["confidence"] = 50

    facts = DrawingFacts(**raw)

    # Сохраняем в кэш
    cache_put(cache_key, "facts", raw)

    print(f"[ЭТАП 1] Факты: тип={facts.detail_type}, материал={facts.material}, "
          f"сварка={facts.has_welding}, мехобр={facts.has_machining}, "
          f"покраска={facts.has_painting}, confidence={facts.confidence}", flush=True)

    return facts, llm_metrics
