"""Сервис бизнес-правил нормирования.

Загружает правила из rules/business_rules.md и логирует нарушения обратно в файл.
"""

import os
from datetime import datetime

_RULES_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rules", "business_rules.md")
_ACTIVE_SECTION = "## Активные правила"
_VIOLATIONS_SECTION = "## Случаи для пересмотра"


def load_rules() -> str:
    """Читает раздел «Активные правила» из файла правил.

    Возвращает текст правил (без заголовков и комментариев),
    или пустую строку если файл не найден / правил нет.
    """
    if not os.path.exists(_RULES_FILE):
        return ""

    try:
        with open(_RULES_FILE, encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"[ПРАВИЛА] Ошибка чтения файла правил: {e}", flush=True)
        return ""

    # Вырезаем раздел «Активные правила»
    start = content.find(_ACTIVE_SECTION)
    if start == -1:
        return ""

    end = content.find("\n---\n", start)
    if end == -1:
        section = content[start + len(_ACTIVE_SECTION):]
    else:
        section = content[start + len(_ACTIVE_SECTION):end]

    # Убираем строки-комментарии (<!-- ... -->) и пустые строки
    lines = []
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("<!--") or not stripped:
            continue
        lines.append(stripped)

    return "\n".join(lines)


def log_violation(
    drawing_name: str,
    stage: str,
    llm_choice: str,
    rule_hint: str,
    action_taken: str,
) -> None:
    """Дописывает запись о нарушении правила в раздел «Случаи для пересмотра».

    Args:
        drawing_name: имя чертежа/файла
        stage: этап конвейера («выбор маршрута», «выбор оборудования»)
        llm_choice: что выбрала LLM
        rule_hint: какое правило нарушено (краткий текст)
        action_taken: что система сделала (заменила, предупредила)
    """
    if not os.path.exists(_RULES_FILE):
        return

    try:
        with open(_RULES_FILE, encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"[ПРАВИЛА] Ошибка чтения для записи нарушения: {e}", flush=True)
        return

    date_str = datetime.now().strftime("%Y-%m-%d")
    entry = (
        f"\n<!-- ПЕРЕСМОТРЕТЬ: {date_str} | Чертёж: {drawing_name} | Этап: {stage} -->\n"
        f"LLM выбрала: {llm_choice}\n"
        f"Нарушено правило: {rule_hint}\n"
        f"Действие системы: {action_taken}\n"
        f"---\n"
    )

    # Вставляем запись перед закрывающим комментарием раздела или в конец
    violations_pos = content.find(_VIOLATIONS_SECTION)
    if violations_pos != -1:
        # Вставляем в конец файла (после заголовка секции нарушений)
        new_content = content + entry
    else:
        # Если секции нет — добавляем её целиком
        new_content = content + f"\n---\n\n{_VIOLATIONS_SECTION}\n\n{entry}"

    try:
        with open(_RULES_FILE, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"[ПРАВИЛА] Нарушение правила залогировано: {drawing_name} / {stage}", flush=True)
    except Exception as e:
        print(f"[ПРАВИЛА] Ошибка записи нарушения: {e}", flush=True)
