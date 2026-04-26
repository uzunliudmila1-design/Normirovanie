"""Промпт для этапа 3: выбор маршрута из shortlist."""

_CHOOSE_ROUTE_BASE = """You are a manufacturing process engineer. You are given:
1. Facts about a part (type, material, operation flags).
2. A short list of candidate routes (3-5) with relevance scores.

Select the ONE most suitable route.

Return strictly JSON:
{
  "route_id": "M-XXXX",
  "confidence": 0-100,
  "reasoning": "structured reasoning (see format below)"
}

REASONING FORMAT (strictly follow):
- Describe EACH candidate route on a SEPARATE line, starting with its ID
- After all routes, add a blank line and your final verdict in bold: **Вывод: ...**

Example reasoning value:
"М-0026 (оценка 0.85): подходит по типу детали и материалу, содержит все необходимые операции.\nМ-0031 (оценка 0.70): не содержит операции шлифования, которая требуется по чертежу.\nМ-0044 (оценка 0.65): избыточен — включает термообработку, не требующуюся для данной детали.\n\n**Вывод: маршрут М-0026 оптимален — полное совпадение операций без лишних этапов, наивысшая оценка совпадения.**"

Rules:
- Select ONLY from the provided list
- Consider part type, material, and operation flags
- If no route fits well — pick the best available but set confidence < 50
- JSON only, no text before or after
- The "reasoning" value must be in Russian
- Use \\n for line breaks inside the JSON string
"""


def build_choose_route_prompt(rules_text: str = "", operations_text: str = "") -> str:
    """Возвращает системный промпт для выбора маршрута.

    Если переданы бизнес-правила — вставляет их как обязательный блок.
    Если передан справочник операций — добавляет его как справочную информацию.
    """
    prompt = _CHOOSE_ROUTE_BASE

    if operations_text and operations_text.strip():
        prompt += (
            "\n\nOPERATIONS REFERENCE (conditions when each operation applies):\n"
            + operations_text.strip()
            + "\n"
        )

    if rules_text and rules_text.strip():
        prompt += (
            "\n\nMANDATORY BUSINESS RULES (set by the company technologist — "
            "these OVERRIDE your judgment if there is any conflict):\n"
            + rules_text.strip()
            + "\nYou MUST follow these rules exactly. "
            "If your preferred choice would violate them, choose differently and explain why in the reasoning.\n"
        )

    return prompt


# Обратная совместимость: константа без правил
CHOOSE_ROUTE_PROMPT = _CHOOSE_ROUTE_BASE

# --- ПЕРЕВОД (только для чтения — в LLM не отправляется) ---
_CHOOSE_ROUTE_PROMPT_RU = """
Ты — технолог производства. Тебе даны:
1. Факты о детали (тип, материал, флаги операций).
2. Короткий список маршрутов-кандидатов (3–5) с оценками релевантности.

Выбрать ОДИН наиболее подходящий маршрут.

Вернуть строго JSON:
{
  "route_id": "M-XXXX",
  "confidence": 0-100,
  "reasoning": "структурированное обоснование (см. формат ниже)"
}

ФОРМАТ ОБОСНОВАНИЯ (соблюдать строго):
- Описать КАЖДЫЙ маршрут-кандидат на ОТДЕЛЬНОЙ строке, начиная с его ID
- После всех маршрутов — пустая строка и итоговый вывод жирным: **Вывод: ...**

Правила:
- Выбирать ТОЛЬКО из предоставленного списка
- Учитывать тип детали, материал и флаги операций
- Если ни один маршрут не подходит — выбрать лучший, но поставить confidence < 50
- Только JSON, без текста до и после
- Поле "reasoning" — на русском языке
- Переносы строк внутри JSON-строки через \\n
"""
