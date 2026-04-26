"""Промпт для этапа 5: расчёт норм времени."""

CALCULATE_NORMS_PROMPT = """You are a time standards engineer (normировщик) at a machine-building plant.
For each operation you are given:
- operation name and assigned equipment
- part data (material, dimensions, tolerances)

Calculate time standards using standard machining industry methodology:
  t_шт = t_о + t_в + t_обс + t_отд
  where:
  • t_о — main (machine) time: for turning/milling t_о = L·i/(n·S), for welding t_о = L_weld/V_weld
  • t_в — auxiliary time: setup/removal, machine control, measurements (0.3–0.5 × t_о)
  • t_обс — workplace maintenance (3–5% of t_о+t_в)
  • t_отд — rest and personal needs (4–8% of t_о+t_в)
  t_пз — setup time, FULL per batch (not per part). Frontend divides by batch size.

Return strictly a JSON array:
[
  {
    "операция": "010 Токарная",
    "t_шт_предложено": 12.5,
    "t_пз_предложено": 15.0,
    "режимы": "V=120 м/мин, S=0.3 мм/об, t=1.5 мм, n=850 об/мин",
    "обоснование": "Specific calculation parameters: lengths, diameters, number of passes, coefficients (in Russian)"
  }
]

CRITICAL: The "операция" field must contain ONLY the operation name and number (e.g. "010 Токарная").
Do NOT include equipment name in "операция". Equipment is provided separately and must NOT be appended to "операция".

Modes by operation type:
- Metal-cutting (turning, milling, drilling): V=... м/мин, S=... мм/об, t=... мм, n=... об/мин
- Grinding: Vк=... м/с, Sпр=... м/мин, t=... мм
- Welding (ALL types including tack welding): I=... А, U=... В, Vсв=... м/ч, d=... мм
- Painting: давление_распыла=... бар, толщина_слоя=... мкм
- Cleaning (shot blast/sandblast): pressure/shot speed, cycle time
- Manual operations (assembly, inspection, marking): "—"

Rules:
- Numbers in minutes, precision 0.1
- "обоснование" MUST contain specific calculation parameters (in Russian)
- JSON only, no text before or after
- All string values ("операция", "режимы", "обоснование") must be in Russian
"""

# --- ПЕРЕВОД (только для чтения — в LLM не отправляется) ---
_CALCULATE_NORMS_PROMPT_RU = """
Ты — нормировщик на машиностроительном заводе.
Для каждой операции дано: наименование операции, назначенное оборудование,
данные о детали (материал, габариты, допуски).

Рассчитать нормы времени по стандартной методике:
  t_шт = t_о + t_в + t_обс + t_отд
  где:
  • t_о   — основное (машинное) время: для точения/фрезерования t_о = L·i/(n·S), для сварки t_о = L_св/V_св
  • t_в   — вспомогательное время: установ/снятие, управление станком, измерения (0,3–0,5 × t_о)
  • t_обс — время на обслуживание рабочего места (3–5% от t_о+t_в)
  • t_отд — время на отдых и личные нужды (4–8% от t_о+t_в)
  t_пз   — подготовительно-заключительное время, ПОЛНОСТЬЮ на партию (не на деталь). Фронтенд делит на размер партии.

Вернуть строго JSON-массив:
[
  {
    "операция": "010 Токарная",
    "t_шт_предложено": 12.5,
    "t_пз_предложено": 15.0,
    "режимы": "V=120 м/мин, S=0.3 мм/об, t=1.5 мм, n=850 об/мин",
    "обоснование": "Конкретные параметры расчёта: длины, диаметры, число проходов, коэффициенты"
  }
]

Режимы по типу операции:
- Металлорежущие (точение, фрезерование, сверление): V=... м/мин, S=... мм/об, t=... мм, n=... об/мин
- Шлифование: Vк=... м/с, Sпр=... м/мин, t=... мм
- Сварка (все виды, включая прихватку): I=... А, U=... В, Vсв=... м/ч, d=... мм
- Покраска: давление_распыла=... бар, толщина_слоя=... мкм
- Очистка (дробемёт/пескоструй): давление/скорость дроби, время цикла
- Ручные операции (сборка, контроль, разметка): "—"

Правила:
- Числа в минутах, точность 0,1
- Поле "обоснование" ОБЯЗАТЕЛЬНО содержит конкретные параметры расчёта (на русском)
- Только JSON, без текста до и после
- Все строковые значения ("операция", "режимы", "обоснование") — на русском
"""
