#!/bin/bash
cd "$(dirname "$0")"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export LANG=${LANG:-ru_RU.UTF-8}

# Используем venv в /tmp/norm_venv, если он есть и рабочий; иначе системный python3
if [ -x /tmp/norm_venv/bin/python3 ] && /tmp/norm_venv/bin/python3 -c "import flask" >/dev/null 2>&1; then
    PYTHON=/tmp/norm_venv/bin/python3
else
    PYTHON=$(command -v python3)
fi

exec "$PYTHON" app.py
