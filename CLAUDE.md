# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Язык общения

Всегда общаться с пользователем **на русском языке**. Все ответы, пояснения, комментарии и сообщения об ошибках должны быть на русском.

## О проекте

Веб-приложение для автоматического расчёта норм времени производственных операций (t_шт, t_пз) на машиностроительном заводе. Два режима:
- **Режим А** (чертёж + МК): нормирование операций из маршрутной карты
- **Режим Б** (только чертёж): автоматический подбор типового маршрута из каталога + нормирование

## Запуск

```bash
./run.sh                  # рекомендуется, настраивает UTF-8
python3 app.py            # или напрямую
```

Порт **5050**. Debug управляется через `FLASK_DEBUG`.

## Настройка окружения

```
USE_CLAUDE_CODE=true        # по умолчанию — Claude Code CLI (подписка)
USE_STUB=false              # true — тестовые данные без LLM
# CLAUDE_BIN=/path/to/claude
```

## Установка зависимостей

```bash
pip install -r requirements.txt
```

Зависимости: `flask`, `anthropic`, `python-dotenv`, `openpyxl`, `pydantic`.

## Архитектура

Конвейер из 6 этапов — код управляет процессом, LLM помогает на узких местах:

```
Этап 1  extract_facts      → DrawingFacts         (LLM: только факты из чертежа)
Этап 2  route_filter        → 5 кандидатов         (КОД: фильтрация по признакам)
Этап 3  route_selection     → SelectedRoute        (КОД или LLM из shortlist)
Этап 4  equipment_filter    → EquipmentChoice[]    (КОД + LLM для неоднозначных)
Этап 5  norm_calculation    → OperationNorm[]      (LLM с узким промптом)
Этап 6  validation          → warnings[]           (КОД: логические проверки)
```

### Структура файлов

```
app.py                          — Flask-роуты и запуск
config.py                       — настройки, пути, проверки при старте

models/
  schemas.py                    — Pydantic-схемы: DrawingFacts, RouteCandidate, SelectedRoute,
                                  EquipmentItem, EquipmentChoice, OperationNorm, PipelineResult

repositories/
  equipment_repository.py       — загрузка из Excel, фильтрация по операции/цеху
  routes_repository.py          — загрузка маршрутов, оценка и фильтрация по фактам

services/
  claude_service.py             — тонкая обёртка LLM (Claude Code CLI primary, API fallback)
  drawing_facts_service.py      — этап 1: извлечение фактов (с кэшированием)
  route_selection_service.py    — этапы 2-3: фильтрация + выбор маршрута (с кэшированием)
  equipment_selection_service.py— этап 4: подбор оборудования
  norm_calculation_service.py   — этап 5: расчёт норм
  validation_service.py         — этап 6: валидация результата
  pipeline_service.py           — оркестратор конвейера
  drawing_analysis_service.py   — анализ чертежа (замечания по ГОСТ)
  cache_service.py              — двухуровневый кэш (память + SQLite)
  db_service.py                 — SQLite

prompts/
  extract_facts.py              — этап 1
  choose_route.py               — этап 3
  choose_equipment.py           — этап 4
  calculate_norms.py            — этап 5
  analyze_drawing.py            — анализ чертежа

templates/index.html            — фронтенд (SPA на ванильном JS)
```

### API эндпоинты

| Метод | Путь | Назначение |
|-------|------|-----------|
| POST | `/api/analyze` | Конвейер нормирования (6 этапов) |
| POST | `/api/analyze_drawing` | Анализ чертежа: замечания и оптимизации |
| POST | `/api/confirm` | Сохранение норм в БД |
| GET | `/api/history` | Последние 200 записей |

## Файлы данных

- `data/equipment.xlsx` — 254 единицы оборудования, индексировано по операциям (39 типов)
- `routes/typical_routes.xlsx` — 236 типовых маршрутов

## Промпты

Промпты в `prompts/` на английском (экономия токенов в KV-кэше), но требуют от модели ответы на русском.

## Кэширование

`services/cache_service.py` — двухуровневый кэш:
- В памяти процесса (быстро, сбрасывается при перезапуске)
- На диске SQLite `cache.db` (переживает перезапуск)
- Кэш по SHA-256 хэшу содержимого PDF
- Кэшируются: этап 1 (факты), этап 3 (выбор маршрута)

## Ключевые принципы

1. **Код управляет** — модель помогает на узких этапах
2. **Маршрут фильтруется кодом** по признакам из чертежа → shortlist 3-5 вариантов
3. **Оборудование фильтруется кодом** по операции + цеху → shortlist для модели
4. **Валидация кодом** ловит противоречия: факты vs маршрут, цех покраски, диапазоны значений
5. **Промпты короткие** — каждый этап получает только нужную информацию
6. **Всегда Claude Code CLI** (подписка), не API-ключ

## Реестр стандартных операций

49 операций утверждены. Частые ошибки в названиях:
- `Внутришлифовальная` (не «Внутришлифовочная»)
- `Долбежная` (не «Долбёжная»)
- `Электромонтажная` (не «Электромонтаж»)
