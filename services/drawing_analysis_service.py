"""Анализ чертежа: замечания по ГОСТ и оптимизации технологичности."""

from prompts.analyze_drawing import DRAWING_SYSTEM_PROMPT
from services.claude_service import call_llm_with_pdf


def analyze_drawing(chertezh_file) -> dict:
    """Анализирует чертёж, возвращает замечания и оптимизации с координатами."""
    user_prompt = (
        "Проведи детальный технический анализ этого чертежа детали.\n"
        "Выяви все замечания (ошибки, нарушения ГОСТ) и оптимизации "
        "(предложения по улучшению технологичности).\n"
        "Для каждого пункта укажи приблизительные координаты на чертеже "
        "(x,y,w,h в процентах от листа).\n"
        "Верни строго JSON-объект по указанному формату."
    )

    result, _metrics = call_llm_with_pdf(
        system_prompt=DRAWING_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        pdf_files=[("Чертёж детали", chertezh_file)],
    )
    return result
