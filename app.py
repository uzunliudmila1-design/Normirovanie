import json
import sqlite3
import traceback
from datetime import datetime

from flask import Flask, request, jsonify, render_template, g

from config import DB_PATH, USE_STUB, DEBUG, PORT, check_data_files
from services.db_service import init_db, get_connection
from services.pipeline_service import run_pipeline
from services.drawing_analysis_service import analyze_drawing

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False


# ─── БД: подключение через Flask g ────────────────────────────────────────────

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = get_connection()
    return db


@app.teardown_appcontext
def close_db(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


# ─── Тестовые данные ──────────────────────────────────────────────────────────

STUB_OPERATIONS = [
    {
        "деталь": "Вал ступенчатый (тестовые данные)",
        "операция": "010 Токарная",
        "t_шт_предложено": 12.5,
        "t_пз_предложено": 15.0,
        "режимы": "V=120 м/мин, S=0.3 мм/об, t=1.5 мм, n=850 об/мин",
        "обоснование": "Черновое и чистовое точение Ø45h6, L=320мм, сталь 45, Ra 1.6",
    },
    {
        "деталь": "Вал ступенчатый (тестовые данные)",
        "операция": "020 Фрезерная",
        "t_шт_предложено": 8.3,
        "t_пз_предложено": 12.0,
        "режимы": "V=80 м/мин, Sz=0.05 мм/зуб, t=5.5 мм, n=1820 об/мин",
        "обоснование": "Фрезерование шпоночного паза 14×5.5мм, концевая фреза Ø14",
    },
    {
        "деталь": "Вал ступенчатый (тестовые данные)",
        "операция": "030 Сверлильная",
        "t_шт_предложено": 4.2,
        "t_пз_предложено": 8.0,
        "режимы": "V=25 м/мин, S=0.12 мм/об, n=1600 об/мин",
        "обоснование": "Сверление центрового отверстия Ø5мм, нарезание резьбы М8",
    },
    {
        "деталь": "Вал ступенчатый (тестовые данные)",
        "операция": "040 Шлифовальная",
        "t_шт_предложено": 18.0,
        "t_пз_предложено": 20.0,
        "режимы": "Vк=35 м/с, Sпр=1.5 м/мин, t=0.02 мм, n=200 об/мин",
        "обоснование": "Круглое шлифование шеек Ø45h6, Ra 0.8, квалитет h6",
    },
]

STUB_DRAWING_RESULT = {
    "summary": "Тестовый анализ чертежа. Обнаружено 3 замечания и 2 оптимизации.",
    "remarks": [
        {
            "id": 1, "type": "замечание", "category": "допуски", "priority": "высокий",
            "title": "Не указан допуск на размер Ø45", "x": 35.0, "y": 40.0, "w": 18.0, "h": 8.0,
            "description": "Для поверхности Ø45 не указан квалитет и поле допуска. Нарушение ГОСТ 2.307.",
            "suggestion": "Добавить обозначение Ø45h6 или Ø45±0.012 в зависимости от требуемой посадки.",
        },
        {
            "id": 2, "type": "замечание", "category": "шероховатость", "priority": "средний",
            "title": "Шероховатость не соответствует квалитету", "x": 55.0, "y": 30.0, "w": 15.0, "h": 10.0,
            "description": "На поверхности IT6 указана шероховатость Ra 3.2, что не соответствует требованиям.",
            "suggestion": "Для квалитета IT6 установить Ra ≤ 1.6 мкм.",
        },
        {
            "id": 3, "type": "оптимизация", "category": "технологичность", "priority": "средний",
            "title": "Нетехнологичный радиус R0.5", "x": 45.0, "y": 60.0, "w": 12.0, "h": 8.0,
            "description": "Радиус скругления R0.5 сложен в изготовлении и требует специального инструмента.",
            "suggestion": "Увеличить до R1.0 — стандартный инструмент, снижение стоимости ~15%.",
        },
    ],
}


# ─── Роуты ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def analyze_route():
    """Конвейер нормирования: 6 этапов, код управляет, модель помогает на узких местах."""
    chertezh = request.files.get("chertezh")
    if not chertezh or chertezh.filename == "":
        return jsonify({"error": "Необходимо загрузить чертёж детали"}), 400

    marshrutnaya = request.files.get("marshrutnaya")
    if marshrutnaya and marshrutnaya.filename == "":
        marshrutnaya = None

    batch_size = request.form.get("batch_size", 1)
    try:
        batch_size = int(batch_size)
        if batch_size < 1:
            batch_size = 1
    except (ValueError, TypeError):
        batch_size = 1

    if USE_STUB:
        return jsonify({
            "operations": STUB_OPERATIONS,
            "маршрут": {},
            "предупреждения": [],
            "stub": True,
        })

    try:
        result = run_pipeline(
            chertezh_file=chertezh,
            marshrutnaya_file=marshrutnaya,
            batch_size=batch_size,
        )
        api_data = result.to_api_dict()
        api_data["stub"] = False
        api_data["operations"] = api_data.pop("операции")
        return jsonify(api_data)

    except Exception as e:
        tb = traceback.format_exc()
        print(tb, flush=True)
        return jsonify({"error": f"{e}\n\nTraceback:\n{tb}"}), 500


@app.route("/api/analyze_drawing", methods=["POST"])
def analyze_drawing_route():
    chertezh = request.files.get("chertezh")
    if not chertezh or chertezh.filename == "":
        return jsonify({"error": "Необходимо загрузить чертёж детали"}), 400

    try:
        if USE_STUB:
            return jsonify(STUB_DRAWING_RESULT)

        result = analyze_drawing(chertezh)
        return jsonify(result)

    except json.JSONDecodeError as e:
        traceback.print_exc()
        return jsonify({"error": f"Не удалось разобрать JSON от API: {str(e)}"}), 500
    except Exception as e:
        tb = traceback.format_exc()
        print(tb, flush=True)
        return jsonify({"error": f"{e}\n\nTraceback:\n{tb}"}), 500


@app.route("/api/confirm", methods=["POST"])
def confirm():
    data = request.get_json()
    if not data or "operations" not in data:
        return jsonify({"error": "Нет данных для сохранения"}), 400

    operations = data["operations"]
    изделие = data.get("изделие", "")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db = get_db()
    saved_ids = []

    try:
        for op in operations:
            cursor = db.execute(
                """
                INSERT INTO нормы
                    (деталь, операция, оборудование, t_шт_предложено, t_шт_подтверждено,
                     t_пз_предложено, t_пз_подтверждено, режимы, обоснование, дата, подтверждено, изделие)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    op.get("деталь", ""),
                    op.get("операция", ""),
                    op.get("оборудование", ""),
                    op.get("t_шт_предложено"),
                    op.get("t_шт_подтверждено", op.get("t_шт_предложено")),
                    op.get("t_пз_предложено"),
                    op.get("t_пз_подтверждено", op.get("t_пз_предложено")),
                    op.get("режимы", ""),
                    op.get("обоснование", ""),
                    now,
                    изделие,
                ),
            )
            saved_ids.append(cursor.lastrowid)
        db.commit()
        return jsonify({"saved": len(saved_ids), "ids": saved_ids})
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500


@app.route("/api/history", methods=["GET"])
def history():
    db = get_db()
    rows = db.execute("SELECT * FROM нормы ORDER BY дата DESC LIMIT 200").fetchall()
    return jsonify([dict(r) for r in rows])


# ─── Каталог изделий ──────────────────────────────────────────────────────────

from flask import send_file
from services.products_service import (
    get_products_tree,
    get_variant_files,
    get_pdf_path,
    get_cached_results,
    analyze_part,
    analyze_drawing_disk,
    extract_bom,
    save_qty,
)


@app.route("/api/products/tree", methods=["GET"])
def products_tree():
    """Дерево типов изделий и вариантов для сайдбара."""
    return jsonify(get_products_tree())


@app.route("/api/products/files", methods=["GET"])
def products_files():
    """Список файлов конкретного варианта изделия."""
    ptype = request.args.get("type", "")
    variant = request.args.get("variant", "")
    if not ptype or not variant:
        return jsonify({"error": "Параметры type и variant обязательны"}), 400

    result = get_variant_files(ptype, variant)
    if result is None:
        return jsonify({"error": "Вариант не найден"}), 404
    return jsonify(result)


@app.route("/api/products/pdf", methods=["GET"])
def products_pdf():
    """Отдаёт PDF-файл изделия."""
    ptype = request.args.get("type", "")
    variant = request.args.get("variant", "")
    fpath = request.args.get("path", "")
    if not ptype or not variant or not fpath:
        return jsonify({"error": "Параметры type, variant и path обязательны"}), 400

    if not fpath.lower().endswith(".pdf"):
        return jsonify({"error": "Допустимы только PDF-файлы"}), 400

    full = get_pdf_path(ptype, variant, fpath)
    if not full:
        return jsonify({"error": "Файл не найден"}), 404

    return send_file(full, mimetype="application/pdf")


@app.route("/api/products/results", methods=["GET"])
def products_results():
    """Возвращает кэшированные результаты анализа для варианта изделия."""
    ptype = request.args.get("type", "")
    variant = request.args.get("variant", "")
    if not ptype or not variant:
        return jsonify({"error": "Параметры type и variant обязательны"}), 400

    cache = get_cached_results(ptype, variant)
    if cache is None:
        return jsonify({"error": "Вариант не найден"}), 404
    return jsonify({"results": cache})


@app.route("/api/products/analyze_part", methods=["POST"])
def products_analyze_part():
    """Анализирует один PDF из папки изделия и кэширует результат."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Тело запроса пустое"}), 400

    try:
        result = analyze_part(
            ptype=data.get("type", ""),
            variant=data.get("variant", ""),
            filename=data.get("filename", ""),
        )
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/products/analyze_drawing", methods=["POST"])
def products_analyze_drawing():
    """Анализ чертежа детали из папки изделия."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Тело запроса пустое"}), 400

    try:
        result = analyze_drawing_disk(
            ptype=data.get("type", ""),
            variant=data.get("variant", ""),
            filename=data.get("filename", ""),
        )
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/products/extract_bom", methods=["POST"])
def products_extract_bom():
    """Извлекает спецификацию из сборочного чертежа."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Тело запроса пустое"}), 400

    try:
        bom = extract_bom(
            ptype=data.get("type", ""),
            variant=data.get("variant", ""),
            assembly_file=data.get("assembly_file", ""),
        )
        return jsonify({"bom": bom})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/products/save_qty", methods=["POST"])
def products_save_qty():
    """Сохраняет количество деталей в кэш."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Тело запроса пустое"}), 400

    try:
        save_qty(
            ptype=data.get("type", ""),
            variant=data.get("variant", ""),
            filename=data.get("filename", ""),
            qty=data.get("qty", 1),
        )
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Запуск ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    warnings = check_data_files()
    for w in warnings:
        print(w, flush=True)

    init_db()
    app.run(debug=DEBUG, port=PORT, use_reloader=False)
