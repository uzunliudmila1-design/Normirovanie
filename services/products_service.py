"""Сервис каталога изделий: дерево, анализ PDF с диска, BOM, кэш результатов.

Работает с папкой Изделия/ в корне проекта.
Структура:  Изделия / <тип> / <вариант> / файлы.pdf

Анализ деталей идёт через конвейер 6 этапов (pipeline_service).
"""

import os
import re
import json
from datetime import datetime

from config import PRODUCTS_BASE_PATH, USE_STUB
from services.claude_service import call_llm_with_pdf
from services.pipeline_service import run_pipeline

# ─── Кэш-файл в папке варианта ───────────────────────────────────────────────

PRODUCTS_CACHE_FILE = "_norming_results.json"


# ─── Тестовые данные (stub) ───────────────────────────────────────────────────

_STUB_OPERATIONS = [
    {
        "деталь": "Тестовая деталь (stub)",
        "операция": "010 Токарная",
        "оборудование": "—",
        "t_шт_предложено": 10.0,
        "t_пз_предложено": 15.0,
        "режимы": "—",
        "обоснование": "Тестовые данные",
    }
]


# ─── Утилиты: безопасный путь, кэш ──────────────────────────────────────────

def _safe_products_path(*parts: str) -> str | None:
    """Собирает путь внутри PRODUCTS_BASE_PATH, защита от path traversal."""
    full = os.path.realpath(os.path.join(PRODUCTS_BASE_PATH, *parts))
    base = os.path.realpath(PRODUCTS_BASE_PATH)
    if not full.startswith(base + os.sep) and full != base:
        return None
    return full


def _load_products_cache(variant_path: str) -> dict:
    """Загружает кэш результатов анализа из папки варианта."""
    cache_path = os.path.join(variant_path, PRODUCTS_CACHE_FILE)
    if os.path.isfile(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_products_cache(variant_path: str, cache: dict) -> None:
    """Сохраняет кэш результатов анализа в папку варианта."""
    cache_path = os.path.join(variant_path, PRODUCTS_CACHE_FILE)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _is_assembly_drawing(filename: str) -> bool:
    """Проверяет, является ли файл сборочным чертежом (СБ)."""
    name = os.path.basename(filename)
    return bool(
        re.search(r"\bСБ\b", name, re.IGNORECASE)
        or re.search(r"сборочн", name, re.IGNORECASE)
    )


# ─── Публичные функции (вызываются из роутов) ────────────────────────────────

def get_products_tree() -> dict:
    """Дерево типов изделий и вариантов для сайдбара."""
    base = os.path.realpath(PRODUCTS_BASE_PATH)
    if not os.path.isdir(base):
        return {"types": []}

    types = []
    for type_name in sorted(os.listdir(base)):
        type_path = os.path.join(base, type_name)
        if type_name.startswith(".") or not os.path.isdir(type_path):
            continue
        variants = []
        for var_name in sorted(os.listdir(type_path)):
            var_path = os.path.join(type_path, var_name)
            if var_name.startswith(".") or not os.path.isdir(var_path):
                continue
            has_pdf = any(
                f.lower().endswith(".pdf")
                for dirpath, _, files in os.walk(var_path)
                for f in files
            )
            variants.append({"name": var_name, "empty": not has_pdf})
        types.append({"name": type_name, "variants": variants})
    return {"types": types}


def get_variant_files(ptype: str, variant: str) -> dict | None:
    """Список файлов конкретного варианта изделия. None если не найден."""
    var_path = _safe_products_path(ptype, variant)
    if not var_path or not os.path.isdir(var_path):
        return None

    def scan_dir(dirpath, rel_prefix=""):
        entries = []
        items = sorted(os.listdir(dirpath))
        dirs = [
            i for i in items
            if not i.startswith(".") and os.path.isdir(os.path.join(dirpath, i))
        ]
        files = [
            i for i in items
            if not i.startswith(".")
            and i.lower().endswith(".pdf")
            and os.path.isfile(os.path.join(dirpath, i))
        ]
        for d in dirs:
            children = scan_dir(os.path.join(dirpath, d), rel_prefix + d + "/")
            if children:
                entries.append({
                    "path": rel_prefix + d,
                    "name": d,
                    "type": "dir",
                    "children": children,
                })
        for f in files:
            entries.append({"path": rel_prefix + f, "name": f, "type": "file"})
        return entries

    tree = scan_dir(var_path)
    return {"variant": variant, "tree": tree}


def get_pdf_path(ptype: str, variant: str, fpath: str) -> str | None:
    """Возвращает абсолютный путь к PDF-файлу или None."""
    if not fpath.lower().endswith(".pdf"):
        return None
    full = _safe_products_path(ptype, variant, fpath)
    if not full or not os.path.isfile(full):
        return None
    return full


def get_cached_results(ptype: str, variant: str) -> dict | None:
    """Возвращает кэшированные результаты анализа варианта. None если не найден."""
    var_path = _safe_products_path(ptype, variant)
    if not var_path or not os.path.isdir(var_path):
        return None
    return _load_products_cache(var_path)


# ─── Анализ PDF с диска ──────────────────────────────────────────────────────

def analyze_part(ptype: str, variant: str, filename: str) -> dict:
    """Анализирует один PDF из папки изделия через конвейер 6 этапов.

    Raises ValueError при ошибках валидации, RuntimeError при ошибках анализа.
    """
    if not filename.lower().endswith(".pdf"):
        raise ValueError("Допустимы только PDF-файлы")

    var_path = _safe_products_path(ptype, variant)
    if not var_path or not os.path.isdir(var_path):
        raise ValueError("Вариант не найден")

    pdf_full = _safe_products_path(ptype, variant, filename)
    if not pdf_full or not os.path.isfile(pdf_full):
        raise ValueError("Файл не найден")

    print(f"[КАТАЛОГ] Анализ через конвейер: {variant} / {filename}", flush=True)

    if USE_STUB:
        operations = list(_STUB_OPERATIONS)
        route = {}
    else:
        # Конвейер 6 этапов: факты → маршрут → оборудование → нормы → валидация
        pipeline_result = run_pipeline(
            chertezh_file=pdf_full,  # путь к файлу на диске
            marshrutnaya_file=None,
            batch_size=1,
        )
        api_data = pipeline_result.to_api_dict()
        operations = [op.to_api_dict() for op in pipeline_result.operations]
        route = api_data.get("маршрут", {})

    # Кэшируем
    cache = _load_products_cache(var_path)
    cache[filename] = {
        "operations": operations,
        "route": route,
        "analyzed_at": datetime.now().isoformat(),
    }
    if USE_STUB:
        pass
    elif pipeline_result.warnings:
        cache[filename]["warnings"] = pipeline_result.warnings
    if not USE_STUB and pipeline_result.metrics:
        cache[filename]["metrics"] = pipeline_result.metrics.to_dict()
    _save_products_cache(var_path, cache)
    print(f"[КАТАЛОГ] Сохранено в кэш ({len(operations)} операций)", flush=True)

    return {"filename": filename, "operations": operations, "route": route}


def analyze_drawing_disk(ptype: str, variant: str, filename: str) -> dict:
    """Анализ чертежа детали из папки изделия (замечания/оптимизации).

    Raises ValueError / RuntimeError.
    """
    if not ptype or not variant or not filename:
        raise ValueError("Параметры type, variant и filename обязательны")

    pdf_full = _safe_products_path(ptype, variant, filename)
    if not pdf_full or not os.path.isfile(pdf_full):
        raise ValueError("Файл не найден")

    result = _analyze_drawing_from_disk(pdf_full)

    # Кэшируем
    var_path = _safe_products_path(ptype, variant)
    cache = _load_products_cache(var_path)
    if filename not in cache:
        cache[filename] = {}
    cache[filename]["drawing_analysis"] = result
    _save_products_cache(var_path, cache)

    return result


def extract_bom(ptype: str, variant: str, assembly_file: str) -> list[dict]:
    """Извлекает спецификацию (BOM) из сборочного чертежа и сохраняет в кэш.

    Raises ValueError / RuntimeError.
    """
    if not ptype or not variant or not assembly_file:
        raise ValueError("Параметры type, variant и assembly_file обязательны")

    pdf_full = _safe_products_path(ptype, variant, assembly_file)
    if not pdf_full or not os.path.isfile(pdf_full):
        raise ValueError("Сборочный чертёж не найден")

    print(f"[BOM] Извлечение спецификации из {assembly_file}", flush=True)
    bom = _extract_bom_from_assembly(pdf_full)
    print(f"[BOM] Найдено {len(bom)} позиций", flush=True)

    # Кэшируем
    var_path = _safe_products_path(ptype, variant)
    cache = _load_products_cache(var_path)
    cache["_bom"] = bom
    _save_products_cache(var_path, cache)

    return bom


def save_qty(ptype: str, variant: str, filename: str, qty: int) -> None:
    """Сохраняет количество деталей в кэш.

    Raises ValueError если вариант не найден.
    """
    var_path = _safe_products_path(ptype, variant)
    if not var_path or not os.path.isdir(var_path):
        raise ValueError("Вариант не найден")

    cache = _load_products_cache(var_path)
    if filename in cache:
        cache[filename]["qty"] = max(1, int(qty))
    else:
        cache[filename] = {"qty": max(1, int(qty))}
    _save_products_cache(var_path, cache)



def _analyze_drawing_from_disk(pdf_path: str) -> dict:
    """Анализ чертежа с диска — замечания и оптимизации."""
    from prompts.analyze_drawing import DRAWING_SYSTEM_PROMPT

    if USE_STUB:
        return {
            "summary": "Тестовый анализ чертежа.",
            "remarks": [
                {
                    "id": 1,
                    "type": "замечание",
                    "category": "допуски",
                    "priority": "средний",
                    "title": "Тестовое замечание",
                    "description": "Описание.",
                    "suggestion": "Рекомендация.",
                    "x": 50, "y": 50, "w": 10, "h": 10,
                }
            ],
        }

    user_prompt = (
        "Проведи детальный технический анализ этого чертежа детали.\n"
        "Выяви замечания (ошибки, нарушения ГОСТ) и оптимизации "
        "(предложения по улучшению технологичности).\n"
        "Для каждого пункта укажи приблизительные координаты на чертеже "
        "(x,y,w,h в процентах от листа).\n"
        "Верни строго JSON-объект по указанному формату."
    )

    result, _metrics = call_llm_with_pdf(
        system_prompt=DRAWING_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        pdf_files=[("Чертёж детали", pdf_path)],
    )

    # Нормализуем поля замечаний — модель может вернуть русские ключи
    for r in result.get("remarks", []):
        if "type" not in r and "тип" in r:
            r["type"] = r.pop("тип")
        if "priority" not in r and "приоритет" in r:
            r["priority"] = r.pop("приоритет")
        if "category" not in r and "категория" in r:
            r["category"] = r.pop("категория")
        if "title" not in r:
            r["title"] = r.pop("заголовок", r.pop("название", ""))
        if "description" not in r:
            r["description"] = r.pop("описание", "")
        if "suggestion" not in r:
            r["suggestion"] = r.pop("рекомендация", "")

    return result


# ─── BOM ──────────────────────────────────────────────────────────────────────

BOM_PROMPT = """Проанализируй сборочный чертёж и извлеки спецификацию (ведомость деталей).

Верни ТОЛЬКО JSON объект в формате:
{
  "bom": [
    {"деталь": "название детали", "количество": 4},
    {"деталь": "другая деталь", "количество": 2}
  ]
}

Извлеки ВСЕ детали из спецификации/штампа чертежа с их количеством.
Названия деталей пиши так, как они указаны в чертеже.
Верни ТОЛЬКО JSON, без пояснений."""

BOM_SYSTEM_PROMPT = (
    "Ты — конструктор. Извлеки спецификацию (BOM) из сборочного чертежа. "
    "Верни строго JSON."
)


def _extract_bom_from_assembly(pdf_path: str) -> list[dict]:
    """Извлекает спецификацию (BOM) из сборочного чертежа."""
    if USE_STUB:
        return []

    result, _metrics = call_llm_with_pdf(
        system_prompt=BOM_SYSTEM_PROMPT,
        user_prompt=BOM_PROMPT,
        pdf_files=[("Сборочный чертёж", pdf_path)],
    )

    if isinstance(result, dict):
        return result.get("bom", [])
    return []
