"""Анализ чертежа: замечания по ГОСТ и оптимизации технологичности."""

import re
from prompts.analyze_drawing import DRAWING_SYSTEM_PROMPT
from prompts.verify_gost import VERIFY_GOST_SYSTEM_PROMPT
from services.claude_service import call_llm_with_pdf, call_llm_with_websearch

# Паттерны нормативных документов (все типы)
_STANDARD_PATTERNS = [
    # ГОСТ, ГОСТ Р, ГОСТ РВ, ГОСТ ISO
    r'ГОСТ\s*(?:Р\s*|РВ\s*|ISO\s*)?[\w\.\-]+(?:\s*-\s*\d{2,4})?',
    # ОСТ (отраслевые)
    r'ОСТ\s*[\w\.\-]+(?:\s*-\s*\d{2,4})?',
    # СТП, СТО (предприятие/организация)
    r'СТ[ПО]\s*[\w\.\-]+(?:\s*-\s*\d{2,4})?',
    # ТУ (технические условия)
    r'ТУ\s*[\w\.\-]+(?:\s*-\s*\d{2,4})?',
    # СНиП
    r'СНиП\s*[\w\.\-]+(?:\s*-\s*\d{2,4})?',
    # СП (своды правил)
    r'СП\s+\d[\w\.\-]*(?:\s*-\s*\d{2,4})?',
    # РД (руководящие документы)
    r'РД\s*[\w\.\-]+(?:\s*-\s*\d{2,4})?',
    # ISO
    r'ISO\s*[\w\.\-:]+(?:\s*-\s*\d{2,4})?',
    # DIN
    r'DIN\s*(?:EN\s*)?[\w\.\-]+(?:\s*-\s*\d{2,4})?',
    # EN (европейские)
    r'EN\s*[\w\.\-]+(?:\s*-\s*\d{2,4})?',
]

_COMBINED_PATTERN = re.compile(
    '|'.join(f'(?:{p})' for p in _STANDARD_PATTERNS),
    re.IGNORECASE
)


def _extract_standards(remarks: list[dict]) -> list[str]:
    """Извлекает уникальные обозначения нормативных документов из замечаний."""
    standards = set()
    for r in remarks:
        for field in ('description', 'suggestion', 'title'):
            text = r.get(field, '')
            if text:
                for m in _COMBINED_PATTERN.finditer(text):
                    standards.add(m.group(0).strip())
    return sorted(standards)


def _verify_standards(std_list: list[str]) -> dict:
    """Проверяет актуальность нормативных документов через веб-поиск.

    Возвращает {обозначение: info}.
    """
    if not std_list:
        return {}

    prompt = (
        "Проверь актуальность следующих нормативных документов. "
        "Для каждого найди в интернете: действует ли он сейчас, или заменён/отменён. "
        "Если заменён — укажи номер и название нового документа.\n\n"
        "Документы для проверки:\n"
        + "\n".join(f"- {s}" for s in std_list)
        + "\n\nВерни строго JSON по указанному формату."
    )

    try:
        result, _metrics = call_llm_with_websearch(
            system_prompt=VERIFY_GOST_SYSTEM_PROMPT,
            user_prompt=prompt,
        )
        verified = result.get("verified", [])
        return {item["standard"]: item for item in verified if "standard" in item}
    except Exception as e:
        print(f"[НОРМЫ] Ошибка верификации: {e}", flush=True)
        return {}


def _enrich_remarks_with_std_status(remarks: list[dict], std_info: dict) -> list[dict]:
    """Дополняет замечания информацией об актуальности нормативных документов."""
    if not std_info:
        return remarks

    for remark in remarks:
        mentioned = set()
        for field in ('description', 'suggestion', 'title'):
            text = remark.get(field, '')
            if text:
                for m in _COMBINED_PATTERN.finditer(text):
                    mentioned.add(m.group(0).strip())

        outdated = []
        for s in mentioned:
            info = std_info.get(s)
            if info and info.get("status") in ("заменён", "отменён"):
                outdated.append(info)

        if outdated:
            additions = []
            for info in outdated:
                std_name = info.get("standard", "?")
                status = info["status"]
                if status == "заменён" and info.get("replacement"):
                    line = (
                        f"⚠ {std_name} — {status}. "
                        f"Актуальный: {info['replacement']}"
                    )
                    if info.get("replacement_title"):
                        line += f" ({info['replacement_title']})"
                    if info.get("note"):
                        line += f". {info['note']}"
                elif status == "отменён":
                    line = f"⚠ {std_name} — отменён без замены"
                    if info.get("note"):
                        line += f". {info['note']}"
                else:
                    continue
                additions.append(line)

            if additions:
                existing = remark.get("suggestion", "")
                block = "\n".join(additions)
                remark["suggestion"] = (
                    f"{existing}\n\n{block}" if existing else block
                )
                remark["gost_outdated"] = True

    return remarks


def analyze_drawing(chertezh_file) -> dict:
    """Анализирует чертёж, возвращает замечания и оптимизации с координатами.

    После базового анализа проверяет актуальность всех упомянутых нормативных
    документов (ГОСТ, ОСТ, СТП, ТУ, СНиП, СП, РД, ISO, DIN, EN) через веб-поиск.
    """
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

    remarks = result.get("remarks", [])

    # Шаг верификации: проверяем все нормативные документы через интернет
    std_list = _extract_standards(remarks)
    if std_list:
        print(f"[НОРМЫ] Найдено {len(std_list)} документов для проверки: {std_list}", flush=True)
        std_info = _verify_standards(std_list)
        outdated_count = sum(1 for v in std_info.values() if v.get("status") in ("заменён", "отменён"))
        print(f"[НОРМЫ] Проверено: {len(std_info)}, устаревших: {outdated_count}", flush=True)
        result["remarks"] = _enrich_remarks_with_std_status(remarks, std_info)

        if std_info:
            result["standards_verification"] = list(std_info.values())

    return result
