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
./run.sh                  # foreground, UTF-8; жёстко использует /tmp/norm_venv/bin/python3
./start.sh                # фоновый запуск, PID пишется в .server.pid
./stop.sh                 # убивает процесс на порту 5050 и удаляет .server.pid
python3 app.py            # напрямую (если venv не нужен)
```

Порт **5050** (можно переопределить через `PORT`). Debug управляется через `FLASK_DEBUG` (по умолчанию `true`).

`run.sh` ожидает виртуальное окружение в `/tmp/norm_venv` — если его нет, либо создайте его, либо запускайте `python3 app.py`.

## Правило: публичная ссылка через Cloudflare Tunnel

**Каждый раз**, когда пользователь просит «поднять сервер», «запустить проект», «подними локалхост» или эквивалент — после старта Flask на порту 5050 **обязательно** поднимать Cloudflare Quick Tunnel и **сразу выдавать пользователю публичную ссылку** `https://*.trycloudflare.com`. Без этой ссылки пользователь не сможет открыть сервер из браузера.

Алгоритм:

```bash
# 1. Запустить сервер (если ещё не запущен)
cd "<путь к проекту>" && nohup ./run.sh > server.log 2>&1 &

# 2. Дождаться, пока порт 5050 ответит 200
until curl -s -o /dev/null -w "%{http_code}" http://localhost:5050/ | grep -q 200; do sleep 1; done

# 3. Поднять туннель в фоне
rm -f /tmp/cf_tunnel.log
nohup cloudflared tunnel --url http://localhost:5050 --no-autoupdate > /tmp/cf_tunnel.log 2>&1 &

# 4. Достать URL из лога и сообщить пользователю
until grep -qE "https://[a-z0-9-]+\.trycloudflare\.com" /tmp/cf_tunnel.log; do sleep 1; done
grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" /tmp/cf_tunnel.log | head -1
```

`cloudflared` установлен в `/home/coder/.local/bin/cloudflared`. Если перед стартом туннеля уже работает другой `cloudflared` — сначала убить (`pkill cloudflared`), иначе будет два туннеля с разными URL.

Остановить всё: `./stop.sh && pkill cloudflared`.

URL временный (Quick Tunnel) — при каждом перезапуске имя меняется. Это нормально для разработки.

## Настройка окружения

```
USE_CLAUDE_CODE=true                           # по умолчанию — Claude Code CLI (подписка)
USE_STUB=false                                 # true — тестовые данные без LLM
# ANTHROPIC_API_KEY=sk-ant-...                 # только если USE_CLAUDE_CODE=false
# CLAUDE_BIN=/path/to/claude                   # если не задано — ищет claude в PATH / стандартных местах macOS
# CLAUDE_MODEL=claude-sonnet-4-20250514        # модель по умолчанию
# FLASK_DEBUG=true
# PORT=5050
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
  operations_repository.py      — реестр стандартных операций (data/operations.xlsx)

services/
  claude_service.py             — тонкая обёртка LLM (Claude Code CLI primary, API fallback)
  drawing_facts_service.py      — этап 1: извлечение фактов (с кэшированием)
  route_selection_service.py    — этапы 2-3: фильтрация + выбор маршрута (с кэшированием)
  equipment_selection_service.py— этап 4: подбор оборудования
  norm_calculation_service.py   — этап 5: расчёт норм
  validation_service.py         — этап 6: валидация результата
  pipeline_service.py           — оркестратор конвейера + статус (get_analysis_status)
  drawing_analysis_service.py   — анализ чертежа (замечания по ГОСТ)
  rules_service.py              — чтение бизнес-правил из rules/business_rules.md
  products_service.py           — каталог изделий: дерево, анализ PDF с диска, BOM, кэш
  cache_service.py              — двухуровневый кэш (память + SQLite)
  db_service.py                 — SQLite (norming.db, таблица «нормы»)

prompts/
  extract_facts.py              — этап 1
  choose_route.py               — этап 3
  choose_equipment.py           — этап 4
  calculate_norms.py            — этап 5
  analyze_drawing.py            — анализ чертежа
  verify_gost.py                — верификация по ГОСТ

templates/index.html            — фронтенд (SPA на ванильном JS)

rules/business_rules.md         — активные бизнес-правила маршрутизации (читается на каждый анализ)
```

### Вспомогательные скрипты в корне

Автономные утилиты, **не подключены** к веб-приложению — запускаются вручную:
- `draw_caliber.py`, `draw_caliber2.py`, `draw_caliber3.py` — генерация PNG чертежей калибра
- `make_presentation.py` — сборка `Презентация_система_нормирования.docx`

### API эндпоинты

Основной поток нормирования:

| Метод | Путь | Назначение |
|-------|------|-----------|
| POST | `/api/analyze` | Конвейер нормирования (6 этапов) |
| POST | `/api/analyze_drawing` | Анализ чертежа: замечания и оптимизации |
| POST | `/api/confirm` | Сохранение норм в БД |
| GET | `/api/history` | Последние 200 записей |

Каталог изделий (работает с папкой `Изделия/`):

| Метод | Путь | Назначение |
|-------|------|-----------|
| GET  | `/api/products/tree` | Дерево «тип → варианты» для сайдбара |
| GET  | `/api/products/files` | Список файлов варианта |
| GET  | `/api/products/pdf` | Отдаёт PDF варианта (защита от path traversal) |
| GET  | `/api/products/results` | Кэшированные результаты анализа варианта |
| GET  | `/api/products/analysis_status` | Текущий этап конвейера (1-6) или idle |
| POST | `/api/products/analyze_part` | Анализ одной детали из папки изделия |
| POST | `/api/products/analyze_drawing` | Анализ чертежа детали из папки изделия |
| POST | `/api/products/extract_bom` | Извлечение спецификации из сборочного чертежа |
| POST | `/api/products/save_qty` | Сохранение количества деталей в кэш |

## Файлы данных

- `data/equipment.xlsx` — 254 единицы оборудования, индексировано по операциям (39 типов)
- `data/operations.xlsx` — реестр из 49 утверждённых наименований операций
- `routes/typical_routes.xlsx` — 236 типовых маршрутов
- `Изделия/<тип>/<вариант>/*.pdf` — каталог сборочных чертежей и деталей; в каждом варианте создаётся `_norming_results.json` с кэшем анализа
- `norming.db` — SQLite с подтверждёнными нормами (таблица `нормы`); создаётся при старте через `init_db()`
- `cache.db` — отдельная SQLite для двухуровневого кэша LLM-этапов (см. ниже)

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
