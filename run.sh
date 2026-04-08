#!/bin/bash
cd "$(dirname "$0")"
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 /tmp/norm_venv/bin/python3 app.py
