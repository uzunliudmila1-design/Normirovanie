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
import os
import time
import sqlite3
import threading
import traceback
import uuid
from datetime import datetime

from config import DB_PATH
from models.schemas import PipelineResult, SelectedRoute, DrawingFacts, StageMetrics, PipelineMetrics
from services.drawing_facts_service import extract_facts
from services.route_selection_service import select_route
from services.equipment_selection_service import select_equipment
from services.norm_calculation_service import calculate_norms
from services.validation_service import validate_result
from services.rules_service import log_violation


# ─── Трекер текущего анализа ─────────────────────────────────────────────────

_status_lock = threading.Lock()
_current_status: dict = {"active": False, "stage": 0, "stage_name": "", "filename": ""}

_STAGE_NAMES = {
    1: "Извлечение фактов из чертежа",
    2: "Фильтрация маршрутов",
    3: "Выбор маршрута",
    4: "Подбор оборудования",
    5: "Расчёт норм времени",
    6: "Валидация",
}


# ─── Фоновые задачи ──────────────────────────────────────────────────────────
# Длинные операции (run_pipeline, analyze_drawing, extract_bom) запускаются в
# отдельном потоке. HTTP-запрос сразу возвращает job_id, фронт опрашивает
# /api/jobs/<id>. Это снимает таймауты прокси/туннеля (Cloudflare Quick Tunnel
# рвёт запросы дольше ~100 сек) и убирает зависание UI.

_jobs_lock = threading.Lock()
_jobs: dict[str, dict] = {}
_thread_state = threading.local()
_MAX_KEEP_FINISHED = 50


def _new_job(filename: str, kind: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "kind": kind,
            "filename": filename,
            "active": True,
            "stage": 0,
            "stage_name": "Запуск",
            "started_at": time.time(),
            "finished_at": None,
            "result": None,
            "error": None,
        }
        finished = [(jid, j.get("finished_at") or 0) for jid, j in _jobs.items() if not j["active"]]
        if len(finished) > _MAX_KEEP_FINISHED:
            finished.sort(key=lambda p: p[1])
            for jid, _ in finished[: len(finished) - _MAX_KEEP_FINISHED]:
                _jobs.pop(jid, None)
    return job_id


def get_job(job_id: str) -> dict | None:
    """Возвращает состояние задачи или None, если такой нет."""
    with _jobs_lock:
        j = _jobs.get(job_id)
        return dict(j) if j else None


def _update_job(job_id: str, **fields) -> None:
    with _jobs_lock:
        j = _jobs.get(job_id)
        if j:
            j.update(fields)


def _job_runner(job_id: str, target, args: tuple, kwargs: dict, cleanup_paths: list[str] | None) -> None:
    _thread_state.job_id = job_id
    try:
        result = target(*args, **kwargs)
        _update_job(
            job_id,
            active=False,
            stage=0,
            stage_name="Готово",
            result=result,
            finished_at=time.time(),
        )
    except Exception as e:
        tb = traceback.format_exc()
        print(tb, flush=True)
        _update_job(
            job_id,
            active=False,
            stage=0,
            stage_name="Ошибка",
            error=f"{e}\n\nTraceback:\n{tb}",
            finished_at=time.time(),
        )
    finally:
        _thread_state.job_id = None
        with _status_lock:
            _current_status.update({"active": False, "stage": 0, "stage_name": "", "filename": ""})
        for p in cleanup_paths or []:
            try:
                os.unlink(p)
            except OSError:
                pass


def start_job(
    target,
    *,
    args: tuple = (),
    kwargs: dict | None = None,
    filename: str = "",
    kind: str = "pipeline",
    cleanup_paths: list[str] | None = None,
) -> str:
    """Запускает target в фоновом потоке, возвращает job_id для опроса."""
    job_id = _new_job(filename, kind)
    t = threading.Thread(
        target=_job_runner,
        args=(job_id, target, args, kwargs or {}, cleanup_paths),
        daemon=True,
    )
    t.start()
    return job_id


def _set_status(stage: int, filename: str = "") -> None:
    job_id = getattr(_thread_state, "job_id", None)
    if job_id:
        with _jobs_lock:
            j = _jobs.get(job_id)
            if j is not None:
                j["stage"] = stage
                j["stage_name"] = _STAGE_NAMES.get(stage, j.get("stage_name", ""))
                if filename:
                    j["filename"] = filename
    with _status_lock:
        _current_status.update({
            "active": stage > 0,
            "stage": stage,
            "stage_name": _STAGE_NAMES.get(stage, ""),
            "filename": filename,
        })


def get_analysis_status() -> dict:
    """Возвращает текущий статус конвейера (для polling с фронтенда)."""
    with _status_lock:
        return dict(_current_status)


def run_pipeline(
    chertezh_file,
    batch_size: int = 1,
    is_assembly: bool = False,
) -> PipelineResult:
    """Полный конвейер нормирования.

    Args:
        chertezh_file: PDF чертежа (обязательно)
        batch_size: размер партии
    """
    print("=" * 60, flush=True)
    print("[КОНВЕЙЕР] Запуск нормирования", flush=True)

    _filename = os.path.basename(str(chertezh_file)) if chertezh_file else ""
    pipeline_t0 = time.monotonic()
    all_stages = []

    try:
        # ── Этап 1: Извлечение фактов ──
        _set_status(1, _filename)
        print("[КОНВЕЙЕР] Этап 1: Извлечение фактов из чертежа...", flush=True)
        t0 = time.monotonic()
        facts, llm_m1 = extract_facts(chertezh_file)

        # Для сборочных чертежей: детали приходят готовыми → сбрасываем признаки резки/мехобработки
        if is_assembly:
            facts.is_assembly = True
            facts.has_cutting = False
            facts.has_machining = False
            facts.has_grinding = False
            facts.has_bending = False
            facts.has_heat_treatment = False
            facts.has_assembly = True
            print("[КОНВЕЙЕР] Сборочный чертёж: признаки резки/мехобработки сброшены", flush=True)

        stage1 = StageMetrics(
            stage="1. Извлечение фактов",
            duration_ms=int((time.monotonic() - t0) * 1000),
            llm_calls=llm_m1,
        )
        all_stages.append(stage1)
        _print_stage_metrics(stage1)

        # ── Этапы 2-3: Выбор маршрута ──
        _set_status(2, _filename)
        t0 = time.monotonic()
        print("[КОНВЕЙЕР] Этапы 2-3: Выбор маршрута из каталога...", flush=True)
        route, llm_m23 = select_route(facts)

        stage23 = StageMetrics(
            stage="2-3. Выбор маршрута",
            duration_ms=int((time.monotonic() - t0) * 1000),
            llm_calls=llm_m23,
        )
        all_stages.append(stage23)
        _print_stage_metrics(stage23)

        # ── Этап 4: Подбор оборудования ──
        _set_status(4, _filename)
        print("[КОНВЕЙЕР] Этап 4: Подбор оборудования...", flush=True)
        t0 = time.monotonic()
        # Формируем нумерованные операции
        if route.operations:
            numbered_ops = []
            for i, op in enumerate(route.operations):
                num = f"{10 + i * 5:03d}"
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
        _set_status(5, _filename)
        print("[КОНВЕЙЕР] Этап 5: Расчёт норм времени...", flush=True)
        t0 = time.monotonic()
        # Перематываем файл, т.к. он мог быть прочитан на этапе 1
        if hasattr(chertezh_file, "seek"):
            chertezh_file.seek(0)

        norms, llm_m5 = calculate_norms(
            operations=numbered_ops,
            equipment_choices=equipment_choices,
            facts=facts,
            chertezh_file=chertezh_file,
            batch_size=batch_size,
        )
        stage5 = StageMetrics(
            stage="5. Расчёт норм",
            duration_ms=int((time.monotonic() - t0) * 1000),
            llm_calls=llm_m5,
        )
        all_stages.append(stage5)
        _print_stage_metrics(stage5)

        # ── Коррекция порядка: очистка всегда после сварки ──
        norms = _fix_cleaning_after_welding(norms)

        # ── Правило 1: отверстия + плазма → убрать Сверлильную ──
        before1 = len(norms)
        norms = _fix_no_drilling_with_plasma(norms, facts)
        if len(norms) == before1:
            print("[ПРАВИЛО 1] Проверка пройдена (Сверлильная не удалялась)", flush=True)

        # ── Правило 4: рихтовка запрещена при толщине < 10 мм ──
        before4 = len(norms)
        norms = _fix_no_richtirovka_thin_metal(norms, facts)
        if len(norms) == before4:
            print("[ПРАВИЛО 4] Проверка пройдена (Рихтовка не удалялась)", flush=True)

        # ── Этап 6: Валидация ──
        _set_status(6, _filename)
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

        # Логируем нарушения бизнес-правил в файл правил
        rule_warnings = [w for w in warnings if w.startswith("[ПРАВИЛО]")]
        for rw in rule_warnings:
            log_violation(
                drawing_name=_filename,
                stage="конвейер (этапы 3-4)",
                llm_choice="см. reasoning в результате",
                rule_hint=rw.replace("[ПРАВИЛО] ", "", 1),
                action_taken="предупреждение добавлено в результат",
            )

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

    finally:
        _set_status(0)


def _fix_cleaning_after_welding(norms):
    """Переносит Очистку дробеметную/пескоструйную после последней сварочной операции.

    Правило: очистка выполняется над уже сваренной конструкцией, поэтому
    она не может стоять до сварки.
    """
    from models.schemas import OperationNorm

    def _is_cleaning(op_name: str) -> bool:
        n = op_name.lower()
        return "дробемет" in n or "пескоструй" in n or "дробеструй" in n

    def _is_welding(op_name: str) -> bool:
        n = op_name.lower()
        return "сварк" in n or "прихватк" in n

    def _op_name(norm) -> str:
        parts = norm.operation.strip().split(None, 1)
        return parts[1] if len(parts) == 2 and parts[0].isdigit() else norm.operation

    cleaning_idx = [i for i, n in enumerate(norms) if _is_cleaning(_op_name(n))]
    welding_idx = [i for i, n in enumerate(norms) if _is_welding(_op_name(n))]

    if not cleaning_idx or not welding_idx:
        return norms

    last_weld = max(welding_idx)
    moved = False
    result = list(norms)
    for ci in sorted(cleaning_idx, reverse=True):
        if ci < last_weld:
            op = result.pop(ci)
            # last_weld сдвинулся на -1 после pop
            insert_at = last_weld  # вставляем после (уже -1 от pop)
            result.insert(insert_at, op)
            moved = True
            print(
                f"[КОНВЕЙЕР] Коррекция: '{op.operation}' перенесена после сварки "
                f"(была поз.{ci + 1}, теперь поз.{insert_at + 1})",
                flush=True,
            )

    if moved:
        # Перенумеровываем операции
        for j, n in enumerate(result):
            num = f"{10 + j * 5:03d}"
            parts = n.operation.strip().split(None, 1)
            if len(parts) == 2 and parts[0].isdigit():
                n.operation = f"{num} {parts[1]}"
            else:
                n.operation = f"{num} {n.operation}"

    return result


_SHEET_METAL_TYPES = ("листов", "ребро", "щека", "фланец", "пластин", "профил", "косынк", "заглушк")


def _is_sheet_metal(facts) -> bool:
    """Листовая деталь — вырезается плазмой/лазером, отверстия тоже режутся."""
    dt = (facts.detail_type or "").lower()
    dn = (facts.detail_name or "").lower()
    return any(k in dt or k in dn for k in _SHEET_METAL_TYPES)


def _fix_no_drilling_with_plasma(norms, facts):
    """Правило 1: если деталь режется плазмой/лазером и есть отверстия —
    убрать Сверлильную и Фрезерную (для листовых деталей).

    Отверстия в листовой плазменной/лазерной детали вырезаются той же резкой.
    """
    def _is_cutting(op: str) -> bool:
        lo = op.lower()
        return "плазм" in lo or "газо-плазм" in lo or "лазерн" in lo

    def _is_drilling(op: str) -> bool:
        return "сверлильн" in op.lower()

    def _is_milling(op: str) -> bool:
        return "фрезерн" in op.lower()

    def _op_name(norm) -> str:
        parts = norm.operation.strip().split(None, 1)
        return parts[1] if len(parts) == 2 and parts[0].isdigit() else norm.operation

    has_cutting = any(_is_cutting(_op_name(n)) for n in norms)
    if not (has_cutting and facts.has_holes):
        return norms

    sheet = _is_sheet_metal(facts)

    def _should_remove(n) -> bool:
        op = _op_name(n)
        if _is_drilling(op):
            return True
        if sheet and _is_milling(op):
            return True
        return False

    filtered = [n for n in norms if not _should_remove(n)]
    removed = len(norms) - len(filtered)
    if removed:
        method = "плазмой/лазером"
        print(f"[ПРАВИЛО 1] Удалено {removed} операций (Сверлильная/Фрезерная) — отверстия режутся {method}", flush=True)
        for j, n in enumerate(filtered):
            num = f"{10 + j * 5:03d}"
            parts = n.operation.strip().split(None, 1)
            if len(parts) == 2 and parts[0].isdigit():
                n.operation = f"{num} {parts[1]}"
    return filtered


def _fix_no_richtirovka_thin_metal(norms, facts):
    """Правило 4 (СТП 005-01): рихтовка применима только при 4 ≤ толщина ≤ 40 И длина ≥ 300."""
    thickness = facts.thickness_mm or facts.height_mm or facts.width_mm
    length = facts.length_mm

    thickness_ok = thickness is not None and 4 <= thickness <= 40
    length_ok = length is None or length >= 300
    if thickness_ok and length_ok:
        return norms  # рихтовка допустима

    def _is_richtirovka(op: str) -> bool:
        return "рихтов" in op.lower() or "правк" in op.lower()

    def _op_name(norm) -> str:
        parts = norm.operation.strip().split(None, 1)
        return parts[1] if len(parts) == 2 and parts[0].isdigit() else norm.operation

    filtered = [n for n in norms if not _is_richtirovka(_op_name(n))]
    removed = len(norms) - len(filtered)
    if removed:
        if thickness is not None and not (4 <= thickness <= 40):
            cause = f"толщина {thickness} мм вне диапазона 4–40 мм"
        elif length is not None and length < 300:
            cause = f"длина {length} мм < 300 мм"
        else:
            cause = "не выполнены условия СТП 005-01 (4 ≤ T ≤ 40 мм И L ≥ 300 мм)"
        print(f"[ПРАВИЛО 4] Удалено {removed} операций «Рихтовка» — {cause}", flush=True)
        for j, n in enumerate(filtered):
            num = f"{10 + j * 5:03d}"
            parts = n.operation.strip().split(None, 1)
            if len(parts) == 2 and parts[0].isdigit():
                n.operation = f"{num} {parts[1]}"
    return filtered


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
