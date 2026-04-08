"""Оркестратор конвейера нормирования.

6 этапов:
1. Извлечение фактов из чертежа (LLM)
2. Фильтрация маршрутов кодом
3. Выбор маршрута (код или LLM из shortlist)
4. Подбор оборудования (код + LLM для неоднозначных)
5. Расчёт норм (LLM с узким промптом)
6. Валидация результата (код)
"""

import json
import time
import sqlite3
from datetime import datetime

from config import DB_PATH
from models.schemas import PipelineResult, SelectedRoute, DrawingFacts, StageMetrics, PipelineMetrics
from services.drawing_facts_service import extract_facts
from services.route_selection_service import select_route, route_from_mk
from services.equipment_selection_service import select_equipment
from services.norm_calculation_service import calculate_norms
from services.validation_service import validate_result


def run_pipeline(
    chertezh_file,
    marshrutnaya_file=None,
    batch_size: int = 1,
    mk_operations: list[str] | None = None,
) -> PipelineResult:
    """Полный конвейер нормирования.

    Args:
        chertezh_file: PDF чертежа (обязательно)
        marshrutnaya_file: PDF маршрутной карты (опционально)
        batch_size: размер партии
        mk_operations: список операций из МК (для Режима А, если уже извлечены)
    """
    print("=" * 60, flush=True)
    print("[КОНВЕЙЕР] Запуск нормирования", flush=True)

    pipeline_t0 = time.monotonic()
    all_stages = []

    # ── Этап 1: Извлечение фактов ──
    print("[КОНВЕЙЕР] Этап 1: Извлечение фактов из чертежа...", flush=True)
    t0 = time.monotonic()
    facts, llm_m1 = extract_facts(chertezh_file, marshrutnaya_file)
    stage1 = StageMetrics(
        stage="1. Извлечение фактов",
        duration_ms=int((time.monotonic() - t0) * 1000),
        llm_calls=llm_m1,
    )
    all_stages.append(stage1)
    _print_stage_metrics(stage1)

    # ── Этапы 2-3: Выбор маршрута ──
    has_mk = marshrutnaya_file is not None
    t0 = time.monotonic()
    if has_mk:
        # Режим А: маршрут из МК — операции извлекает модель на этапе 5
        print("[КОНВЕЙЕР] Этапы 2-3: Режим А — маршрут из маршрутной карты", flush=True)
        route = route_from_mk(mk_operations or [])
        llm_m23 = []
    else:
        # Режим Б: фильтрация + выбор из каталога
        print("[КОНВЕЙЕР] Этапы 2-3: Режим Б — выбор маршрута из каталога...", flush=True)
        route, llm_m23 = select_route(facts)

    stage23 = StageMetrics(
        stage="2-3. Выбор маршрута",
        duration_ms=int((time.monotonic() - t0) * 1000),
        llm_calls=llm_m23,
    )
    all_stages.append(stage23)
    _print_stage_metrics(stage23)

    # ── Этап 4: Подбор оборудования ──
    print("[КОНВЕЙЕР] Этап 4: Подбор оборудования...", flush=True)
    t0 = time.monotonic()
    # Формируем нумерованные операции
    if route.operations:
        numbered_ops = []
        for i, op in enumerate(route.operations):
            num = f"{(i + 1) * 10:03d}"
            # Если операция уже содержит номер — не дублируем
            if op[:3].isdigit():
                numbered_ops.append(op)
            else:
                numbered_ops.append(f"{num} {op}")
    else:
        numbered_ops = []

    equipment_choices, llm_m4 = select_equipment(numbered_ops, facts)
    stage4 = StageMetrics(
        stage="4. Подбор оборудования",
        duration_ms=int((time.monotonic() - t0) * 1000),
        llm_calls=llm_m4,
    )
    all_stages.append(stage4)
    _print_stage_metrics(stage4)

    # ── Этап 5: Расчёт норм ──
    print("[КОНВЕЙЕР] Этап 5: Расчёт норм времени...", flush=True)
    t0 = time.monotonic()
    # Перематываем файлы, т.к. они могли быть прочитаны на этапе 1
    if hasattr(chertezh_file, "seek"):
        chertezh_file.seek(0)
    if marshrutnaya_file and hasattr(marshrutnaya_file, "seek"):
        marshrutnaya_file.seek(0)

    norms, llm_m5 = calculate_norms(
        operations=numbered_ops,
        equipment_choices=equipment_choices,
        facts=facts,
        chertezh_file=chertezh_file,
        marshrutnaya_file=marshrutnaya_file,
        batch_size=batch_size,
    )
    stage5 = StageMetrics(
        stage="5. Расчёт норм",
        duration_ms=int((time.monotonic() - t0) * 1000),
        llm_calls=llm_m5,
    )
    all_stages.append(stage5)
    _print_stage_metrics(stage5)

    # ── Этап 6: Валидация ──
    print("[КОНВЕЙЕР] Этап 6: Валидация результата...", flush=True)
    t0 = time.monotonic()
    warnings = validate_result(facts, route, equipment_choices, norms)
    stage6 = StageMetrics(
        stage="6. Валидация",
        duration_ms=int((time.monotonic() - t0) * 1000),
        llm_calls=[],
    )
    all_stages.append(stage6)
    for w in warnings:
        print(f"  {w}", flush=True)

    # ── Сборка метрик ──
    metrics = PipelineMetrics(
        stages=all_stages,
        total_duration_ms=int((time.monotonic() - pipeline_t0) * 1000),
    )

    result = PipelineResult(
        facts=facts,
        route=route,
        equipment_choices=equipment_choices,
        operations=norms,
        warnings=warnings,
        metrics=metrics,
    )

    _print_summary(metrics, len(norms), len(warnings))
    _save_metrics(metrics, facts.detail_name)

    return result


def _print_stage_metrics(stage: StageMetrics):
    """Выводит метрики этапа в лог."""
    parts = [f"[МЕТРИКИ] {stage.stage}: {stage.duration_ms}мс"]
    if stage.llm_calls:
        total_in = stage.total_input_tokens
        total_out = stage.total_output_tokens
        parts.append(f"токены: {total_in}→{total_out}")
        if stage.total_cost_usd > 0:
            parts.append(f"${stage.total_cost_usd:.4f}")
    else:
        parts.append("(без LLM)")
    print(" | ".join(parts), flush=True)


def _print_summary(metrics: PipelineMetrics, num_ops: int, num_warnings: int):
    """Итоговая сводка в лог."""
    print("=" * 60, flush=True)
    print(f"[КОНВЕЙЕР] Готово: {num_ops} операций, {num_warnings} предупреждений", flush=True)
    print(f"[МЕТРИКИ] Общее время: {metrics.total_duration_ms}мс "
          f"({metrics.total_duration_ms / 1000:.1f} сек)", flush=True)
    total_in = metrics.total_input_tokens
    total_out = metrics.total_output_tokens
    if total_in or total_out:
        print(f"[МЕТРИКИ] Токены: {total_in} входных + {total_out} выходных "
              f"= {total_in + total_out} всего", flush=True)
    total_calls = sum(len(s.llm_calls) for s in metrics.stages)
    print(f"[МЕТРИКИ] Вызовов LLM: {total_calls}", flush=True)
    if metrics.total_cost_usd > 0:
        print(f"[МЕТРИКИ] Стоимость: ${metrics.total_cost_usd:.4f}", flush=True)
    print("=" * 60, flush=True)


def _save_metrics(metrics: PipelineMetrics, detail_name: str = ""):
    """Сохраняет метрики прогона в БД."""
    try:
        db = sqlite3.connect(DB_PATH)
        db.execute(
            """INSERT INTO метрики_прогонов
               (дата, деталь, входные_токены, выходные_токены, всего_токенов,
                время_мс, вызовов_llm, этапы_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                detail_name,
                metrics.total_input_tokens,
                metrics.total_output_tokens,
                metrics.total_input_tokens + metrics.total_output_tokens,
                metrics.total_duration_ms,
                sum(len(s.llm_calls) for s in metrics.stages),
                json.dumps(metrics.to_dict(), ensure_ascii=False),
            ),
        )
        db.commit()
        db.close()
    except Exception as e:
        print(f"[МЕТРИКИ] Ошибка сохранения: {e}", flush=True)
