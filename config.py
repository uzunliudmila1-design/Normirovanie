import os
import sys
import shutil
from dotenv import load_dotenv

load_dotenv()

# ─── UTF-8 ────────────────────────────────────────────────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# ─── Базовые пути ─────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "norming.db")

EQUIPMENT_XLSX = os.path.join(BASE_DIR, "data", "equipment.xlsx")
TYPICAL_ROUTES_XLSX = os.path.join(BASE_DIR, "routes", "typical_routes.xlsx")
PRODUCTS_BASE_PATH = os.path.join(BASE_DIR, "Изделия")

# ─── Claude ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
CLAUDE_BIN = os.getenv("CLAUDE_BIN") or shutil.which("claude") or "claude"

USE_STUB = os.getenv("USE_STUB", "false").lower() == "true"
USE_CLAUDE_CODE = os.getenv("USE_CLAUDE_CODE", "true").lower() == "true"

# ─── Flask ─────────────────────────────────────────────────────────────────────
DEBUG = os.getenv("FLASK_DEBUG", "true").lower() == "true"
PORT = int(os.getenv("PORT", "5050"))


def check_data_files():
    """Проверяет наличие критичных файлов данных при старте.
    Возвращает список предупреждений (пустой, если всё ок).
    """
    warnings = []
    if not os.path.exists(EQUIPMENT_XLSX):
        warnings.append(
            f"[ПРЕДУПРЕЖДЕНИЕ] Файл оборудования не найден: {EQUIPMENT_XLSX}\n"
            f"  Анализ будет работать без базы оборудования завода!"
        )
    if not os.path.exists(TYPICAL_ROUTES_XLSX):
        warnings.append(
            f"[ПРЕДУПРЕЖДЕНИЕ] Файл типовых маршрутов не найден: {TYPICAL_ROUTES_XLSX}\n"
            f"  Режим Б (только чертёж) будет работать без каталога маршрутов!"
        )
    if not ANTHROPIC_API_KEY and not USE_STUB and not USE_CLAUDE_CODE:
        warnings.append(
            "[ПРЕДУПРЕЖДЕНИЕ] ANTHROPIC_API_KEY не задан в .env\n"
            "  Анализ через API не будет работать (используйте USE_CLAUDE_CODE=true или USE_STUB=true)"
        )
    return warnings
