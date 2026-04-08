"""Тонкая обёртка для вызова Claude: API и CLI.

Все вызовы LLM в проекте проходят через этот модуль.
Каждый вызов — с маленьким промптом для конкретного этапа.
"""

import os
import re
import json
import base64
import subprocess
import uuid
import time

from config import CLAUDE_BIN, CLAUDE_MODEL, ANTHROPIC_API_KEY, USE_CLAUDE_CODE, BASE_DIR
from models.schemas import LLMCallMetrics

# Папка для временных PDF (внутри проекта, чтобы CLI имел доступ)
_TMP_DIR = os.path.join(BASE_DIR, ".tmp_pdf")


def _strip_markdown_json(text: str) -> str:
    """Убирает ```json ... ``` обёртку."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])
    return text.strip()


def _extract_json_from_text(text: str) -> str:
    """Извлекает JSON из текста — ищет ```json блок или первый { ... }."""
    # 1. Ищем ```json ... ```
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        return m.group(1).strip()

    # 2. Ищем первый { ... } или [ ... ] с балансировкой скобок
    for start_ch, end_ch in [('{', '}'), ('[', ']')]:
        start = text.find(start_ch)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            c = text[i]
            if escape:
                escape = False
                continue
            if c == '\\' and in_string:
                escape = True
                continue
            if c == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == start_ch:
                depth += 1
            elif c == end_ch:
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]

    return text.strip()


def _parse_json_response(text: str, context: str = "") -> dict:
    """Парсит JSON из ответа LLM с понятной ошибкой."""
    if not text:
        raise RuntimeError(f"LLM вернул пустой ответ ({context})")

    # Пробуем напрямую
    cleaned = _strip_markdown_json(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Пробуем извлечь JSON из текста
    extracted = _extract_json_from_text(text)
    try:
        return json.loads(extracted)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"LLM вернул невалидный JSON ({context}): {e}\n"
            f"Ответ (первые 500 символов): {text[:500]}"
        )


def call_llm_text(system_prompt: str, user_prompt: str) -> tuple[dict, list[LLMCallMetrics]]:
    """Вызывает LLM с текстовым промптом, возвращает (JSON, [метрики])."""
    if USE_CLAUDE_CODE:
        return _call_via_cli(system_prompt, user_prompt)
    else:
        return _call_via_api(system_prompt, user_prompt)


def call_llm_with_pdf(system_prompt: str, user_prompt: str, pdf_files: list) -> tuple[dict, list[LLMCallMetrics]]:
    """Вызывает LLM с PDF-файлами + текстовым промптом.

    pdf_files: список кортежей (label, file_storage_or_path)
    Возвращает (JSON, [метрики]).
    """
    if USE_CLAUDE_CODE:
        return _call_with_pdf_cli(system_prompt, user_prompt, pdf_files)
    else:
        return _call_with_pdf_api(system_prompt, user_prompt, pdf_files)


# ─── API-реализация ───────────────────────────────────────────────────────────

def _get_client():
    from anthropic import Anthropic
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY не задан в .env")
    return Anthropic(api_key=ANTHROPIC_API_KEY)


def _extract_api_metrics(message, duration_ms: int) -> LLMCallMetrics:
    """Извлекает метрики из ответа Anthropic API."""
    usage = getattr(message, "usage", None)
    return LLMCallMetrics(
        input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
        output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
        duration_ms=duration_ms,
        cost_usd=0.0,  # API стоимость считается на стороне Anthropic
    )


def _call_via_api(system_prompt: str, user_prompt: str) -> tuple[dict, list[LLMCallMetrics]]:
    client = _get_client()
    t0 = time.monotonic()
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    duration_ms = int((time.monotonic() - t0) * 1000)
    metrics = _extract_api_metrics(message, duration_ms)
    text = message.content[0].text
    return _parse_json_response(text, "call_via_api"), [metrics]


def _call_with_pdf_api(system_prompt: str, user_prompt: str, pdf_files: list) -> tuple[dict, list[LLMCallMetrics]]:
    client = _get_client()

    content = []
    for label, file_obj in pdf_files:
        content.append({"type": "text", "text": label})
        if hasattr(file_obj, "read"):
            data = base64.standard_b64encode(file_obj.read()).decode("utf-8")
        else:
            with open(file_obj, "rb") as f:
                data = base64.standard_b64encode(f.read()).decode("utf-8")
        content.append({
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": data},
        })
    content.append({"type": "text", "text": user_prompt})

    t0 = time.monotonic()
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": content}],
    )
    duration_ms = int((time.monotonic() - t0) * 1000)
    metrics = _extract_api_metrics(message, duration_ms)
    text = message.content[0].text
    return _parse_json_response(text, "call_with_pdf_api"), [metrics]


# ─── CLI-реализация ───────────────────────────────────────────────────────────

def _run_cli_text(system_prompt: str, prompt: str) -> tuple[str, LLMCallMetrics]:
    """Запускает CLI без tool use — чистый текстовый вызов, output-format json работает.

    Запускается из temp-директории, чтобы CLAUDE.md проекта не влиял на поведение.
    Возвращает (текст ответа, метрики).
    """
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)

    # Запуск из temp чтобы CLAUDE.md не перехватывал поведение CLI
    tmp_dir = env.get("TEMP", env.get("TMP", BASE_DIR))

    print("[CLI] Текстовый вызов...", flush=True)

    t0 = time.monotonic()
    try:
        result = subprocess.run(
            [
                CLAUDE_BIN,
                "-p", "-",
                "--output-format", "json",
                "--system-prompt", system_prompt,
                "--model", "sonnet",
                "--no-session-persistence",
            ],
            capture_output=True,
            timeout=600,
            env=env,
            cwd=tmp_dir,
            input=prompt.encode("utf-8"),
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Claude Code: превышен таймаут (600 сек)")
    except FileNotFoundError:
        raise RuntimeError(f"Claude Code CLI не найден: {CLAUDE_BIN}")

    wall_ms = int((time.monotonic() - t0) * 1000)
    stdout = (result.stdout or b"").decode("utf-8", errors="replace").strip()
    stderr = (result.stderr or b"").decode("utf-8", errors="replace").strip()

    print(f"[CLI] returncode={result.returncode}, stdout={len(stdout)} символов, время={wall_ms}мс", flush=True)

    if result.returncode != 0:
        raise RuntimeError(f"Claude Code ошибка (код {result.returncode}): {stderr[:500]}")

    if not stdout:
        raise RuntimeError(f"Claude Code вернул пустой stdout. stderr: {stderr[:500]}")

    # Парсим JSON-обёртку {"result": "...", "usage": {...}, "cost_usd": ..., "duration_ms": ...}
    metrics = LLMCallMetrics(duration_ms=wall_ms)
    try:
        data = json.loads(stdout)
        if data.get("is_error"):
            raise RuntimeError(f"Claude Code: {data.get('result', 'неизвестная ошибка')}")

        # Извлекаем метрики из CLI JSON
        usage = data.get("usage", {})
        metrics = LLMCallMetrics(
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            duration_ms=data.get("duration_ms", wall_ms),
            cost_usd=data.get("cost_usd", 0.0) or 0.0,
        )
        print(f"[CLI] Метрики: in={metrics.input_tokens}, out={metrics.output_tokens}, "
              f"cost=${metrics.cost_usd:.4f}, time={metrics.duration_ms}мс", flush=True)

        text = data.get("result")
        if text:
            return text, metrics
    except json.JSONDecodeError:
        pass

    return stdout, metrics


def _run_cli_with_read(system_prompt: str, prompt: str) -> tuple[str, LLMCallMetrics]:
    """Запускает CLI с Read tool — output-format json НЕ работает, stdout = текст ответа.

    Возвращает (текст, метрики). Токены недоступны в этом режиме, только время.
    """
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)

    print("[CLI] Вызов с Read...", flush=True)

    t0 = time.monotonic()
    try:
        result = subprocess.run(
            [
                CLAUDE_BIN,
                "-p", prompt,
                "--allowedTools", "Read",
                "--system-prompt", system_prompt,
                "--model", "sonnet",
                "--no-session-persistence",
                "--dangerously-skip-permissions",
            ],
            capture_output=True,
            timeout=600,
            env=env,
            cwd=BASE_DIR,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Claude Code: превышен таймаут (600 сек)")
    except FileNotFoundError:
        raise RuntimeError(f"Claude Code CLI не найден: {CLAUDE_BIN}")

    wall_ms = int((time.monotonic() - t0) * 1000)
    stdout = (result.stdout or b"").decode("utf-8", errors="replace").strip()
    stderr = (result.stderr or b"").decode("utf-8", errors="replace").strip()

    print(f"[CLI] returncode={result.returncode}, stdout={len(stdout)} символов, время={wall_ms}мс", flush=True)

    if result.returncode != 0:
        raise RuntimeError(f"Claude Code ошибка (код {result.returncode}): {stderr[:500]}")

    if not stdout:
        raise RuntimeError(f"Claude Code вернул пустой stdout. stderr: {stderr[:500]}")

    metrics = LLMCallMetrics(duration_ms=wall_ms)
    return stdout, metrics


def _save_pdf_to_project(file_obj) -> str:
    """Сохраняет PDF во временную папку внутри проекта.

    Возвращает ОТНОСИТЕЛЬНЫЙ путь (CLI не работает с длинными путями с кириллицей).
    """
    os.makedirs(_TMP_DIR, exist_ok=True)
    filename = f"{uuid.uuid4().hex[:8]}.pdf"
    rel_path = os.path.join(".tmp_pdf", filename)
    abs_path = os.path.join(BASE_DIR, rel_path)
    if hasattr(file_obj, "save"):
        file_obj.save(abs_path)
    elif hasattr(file_obj, "read"):
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        with open(abs_path, "wb") as f:
            f.write(file_obj.read())
    else:
        with open(file_obj, "rb") as src, open(abs_path, "wb") as dst:
            dst.write(src.read())
    return rel_path


def _run_cli_with_websearch(system_prompt: str, prompt: str) -> tuple[str, LLMCallMetrics]:
    """Запускает CLI с WebSearch/WebFetch — для верификации данных через интернет.

    Возвращает (текст, метрики). output-format json НЕ работает с tools.
    """
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)

    tmp_dir = env.get("TEMP", env.get("TMP", BASE_DIR))

    print("[CLI] Вызов с WebSearch...", flush=True)

    t0 = time.monotonic()
    try:
        result = subprocess.run(
            [
                CLAUDE_BIN,
                "-p", prompt,
                "--allowedTools", "WebSearch,WebFetch",
                "--system-prompt", system_prompt,
                "--model", "sonnet",
                "--no-session-persistence",
                "--dangerously-skip-permissions",
            ],
            capture_output=True,
            timeout=600,
            env=env,
            cwd=tmp_dir,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Claude Code: превышен таймаут (600 сек)")
    except FileNotFoundError:
        raise RuntimeError(f"Claude Code CLI не найден: {CLAUDE_BIN}")

    wall_ms = int((time.monotonic() - t0) * 1000)
    stdout = (result.stdout or b"").decode("utf-8", errors="replace").strip()
    stderr = (result.stderr or b"").decode("utf-8", errors="replace").strip()

    print(f"[CLI] WebSearch returncode={result.returncode}, stdout={len(stdout)} символов, время={wall_ms}мс", flush=True)

    if result.returncode != 0:
        raise RuntimeError(f"Claude Code ошибка (код {result.returncode}): {stderr[:500]}")

    if not stdout:
        raise RuntimeError(f"Claude Code вернул пустой stdout. stderr: {stderr[:500]}")

    metrics = LLMCallMetrics(duration_ms=wall_ms)
    return stdout, metrics


def call_llm_with_websearch(system_prompt: str, user_prompt: str) -> tuple[dict, list[LLMCallMetrics]]:
    """Вызывает LLM с доступом к веб-поиску. Возвращает (JSON, [метрики])."""
    text, metrics = _run_cli_with_websearch(system_prompt, user_prompt)
    return _parse_json_response(text, "call_with_websearch"), [metrics]


def _call_via_cli(system_prompt: str, user_prompt: str) -> tuple[dict, list[LLMCallMetrics]]:
    text, metrics = _run_cli_text(system_prompt, user_prompt)
    return _parse_json_response(text, "call_via_cli"), [metrics]


def _call_with_pdf_cli(system_prompt: str, user_prompt: str, pdf_files: list) -> tuple[dict, list[LLMCallMetrics]]:
    """Двухэтапный вызов CLI для PDF:
    1. CLI с Read: прочитать PDF → получить текстовое описание
    2. CLI без tools: описание + system_prompt → получить JSON (output-format json работает)

    Возвращает (JSON, [метрики шага 1, метрики шага 2]).
    """
    all_metrics = []
    saved_paths = []
    try:
        file_paths = []
        for label, file_obj in pdf_files:
            rel_path = _save_pdf_to_project(file_obj)
            # CLI на Windows: прямые слеши в путях
            rel_path_unix = rel_path.replace("\\", "/")
            abs_path = os.path.join(BASE_DIR, rel_path)
            saved_paths.append(rel_path)
            file_paths.append(rel_path_unix)
            print(f"[CLI] PDF сохранён: {rel_path_unix} ({os.path.getsize(abs_path)} байт)", flush=True)

        # Шаг 1: CLI читает PDF и возвращает текстовое описание
        read_instructions = "\n".join(
            f"Read file {p}" for p in file_paths
        )
        read_prompt = (
            f"{read_instructions}\n\n"
            "Describe in detail everything you see: part type, name, material, dimensions, "
            "mass, all operations, tolerances, surface finish, technical requirements."
        )
        print(f"[CLI] Промпт шага 1: {read_prompt[:200]}...", flush=True)
        pdf_text, m1 = _run_cli_with_read(
            "You read engineering drawings. Describe everything you see in detail.",
            read_prompt,
        )
        all_metrics.append(m1)
        print(f"[CLI] Шаг 1: прочитано {len(pdf_text)} символов: {pdf_text[:200]}", flush=True)

        # Шаг 2: Текстовый вызов (без tools) — output-format json работает
        combined_prompt = (
            f"DOCUMENT CONTENTS:\n{pdf_text}\n\n"
            f"{user_prompt}"
        )
        text, m2 = _run_cli_text(system_prompt, combined_prompt)
        all_metrics.append(m2)
        return _parse_json_response(text, "call_with_pdf_cli"), all_metrics

    finally:
        for p in saved_paths:
            abs_p = os.path.join(BASE_DIR, p) if not os.path.isabs(p) else p
            try:
                os.unlink(abs_p)
            except OSError:
                pass
