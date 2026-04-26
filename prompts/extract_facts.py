"""Промпт для этапа 1: извлечение фактов из чертежа."""

EXTRACT_FACTS_PROMPT = """You are a manufacturing process analyst. Your task is to extract ONLY FACTS from the engineering drawing.

DO NOT select a route. DO NOT select equipment. DO NOT calculate time standards.
Only extract structured information.

Return strictly a JSON object:
{
  "detail_type": "type: листовая | труба | профиль | вал | корпус | фланец | втулка | шестерня | сборка | металлоконструкция | прочее",
  "detail_name": "part name from the drawing",
  "material": "material grade (e.g. Ст3, 09Г2С, 12Х18Н10Т, Сталь 45)",
  "mass_kg": numberOrNull,
  "length_mm": numberOrNull,
  "width_mm": numberOrNull,
  "height_mm": numberOrNull,
  "thickness_mm": numberOrNull,
  "diameter_mm": numberOrNull,

  "has_cutting": true/false,
  "has_bending": true/false,
  "has_welding": true/false,
  "has_machining": true/false,
  "has_grinding": true/false,
  "has_painting": true/false,
  "has_heat_treatment": true/false,
  "has_assembly": true/false,
  "has_cleaning": true/false,
  "has_straightening": true/false,
  "has_holes": true/false,
  "has_threading": true/false,
  "has_slots": true/false,

  "min_tolerance_it": numberOrNull,
  "min_roughness_ra": numberOrNull,
  "has_geometric_tolerances": true/false,

  "workshop": "workshop number from route card or null",

  "confidence": 0-100,
  "confidence_notes": "what is ambiguous or could not be determined"
}

Rules:
- JSON only, no text before or after
- If data is missing → null for numbers, false for flags
- has_cutting = true if cutting/blanking of sheet/tube is visible, or part is clearly made from sheet/profile
- has_welding = true if weld seams are present, weld symbols shown, or part is an assembly of multiple blanks
- has_machining = true if precise dimensions with tolerances IT6-IT12 exist, Ra ≤ 6.3
- has_painting = true if coating, primer, or paint mentioned in technical requirements
- thickness_mm = sheet/wall thickness for flat parts (листовая, ребро, щека, фланец, пластина, профиль). For solid parts (вал, втулка) leave null. Used to determine cutting method: ≤12mm → laser, >12mm → plasma/gas
- confidence: 90+ if drawing is clear, 50-70 if data is sparse, <50 if highly ambiguous
"""

# --- ПЕРЕВОД (только для чтения — в LLM не отправляется) ---
_EXTRACT_FACTS_PROMPT_RU = """
Ты — аналитик производственных процессов. Задача: извлечь ТОЛЬКО ФАКТЫ из чертежа.

НЕ выбирать маршрут. НЕ выбирать оборудование. НЕ рассчитывать нормы времени.
Только структурированная информация.

Вернуть строго JSON-объект:
{
  "detail_type": "тип: листовая | труба | профиль | вал | корпус | фланец | втулка | шестерня | сборка | металлоконструкция | прочее",
  "detail_name": "наименование детали из чертежа",
  "material": "марка материала (напр. Ст3, 09Г2С, 12Х18Н10Т, Сталь 45)",
  "mass_kg": числоИлиNull,
  "length_mm": числоИлиNull,
  "width_mm": числоИлиNull,
  "height_mm": числоИлиNull,
  "diameter_mm": числоИлиNull,

  "has_cutting": true/false,        // резка/вырубка
  "has_bending": true/false,        // гибка
  "has_welding": true/false,        // сварка
  "has_machining": true/false,      // механообработка
  "has_grinding": true/false,       // шлифование
  "has_painting": true/false,       // покраска
  "has_heat_treatment": true/false, // термообработка
  "has_assembly": true/false,       // сборка
  "has_cleaning": true/false,       // очистка
  "has_straightening": true/false,  // правка
  "has_holes": true/false,          // отверстия
  "has_threading": true/false,      // резьба
  "has_slots": true/false,          // пазы

  "min_tolerance_it": числоИлиNull,        // наименьший квалитет (число, напр. 7 для IT7)
  "min_roughness_ra": числоИлиNull,        // наименьший Ra
  "has_geometric_tolerances": true/false,  // геометрические допуски

  "workshop": "номер цеха из маршрутной карты или null",

  "confidence": 0-100,               // уверенность в извлечённых данных
  "confidence_notes": "что неоднозначно или не удалось определить"
}

Правила:
- только JSON, без текста до и после
- данные отсутствуют → null для чисел, false для флагов
- has_cutting = true, если видна резка/вырубка листа/трубы, или деталь явно из листа/профиля
- has_welding = true, если есть швы, символы сварки, или деталь — сборка из нескольких заготовок
- has_machining = true, если есть точные размеры с допусками IT6–IT12, Ra ≤ 6.3
- has_painting = true, если в технических требованиях упоминается покрытие, грунтовка или краска
- confidence: 90+ — чертёж чёткий, 50–70 — данных мало, <50 — высокая неоднозначность
"""
