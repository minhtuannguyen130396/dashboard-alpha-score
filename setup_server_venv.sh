#!/usr/bin/env bash

set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/dashboard-alpha-score}"
VENV_DIR="${VENV_DIR:-$REPO_DIR/.venv}"
BASE_REQ="${BASE_REQ:-$REPO_DIR/requirements.server.txt}"
SENTIMENT_REQ="${SENTIMENT_REQ:-$REPO_DIR/src/sentiment/requirements.txt}"

cd "$REPO_DIR"

echo "========================================"
echo "Server venv setup"
echo "Repo      : $REPO_DIR"
echo "Venv      : $VENV_DIR"
echo "Base req  : $BASE_REQ"
echo "Sent req  : $SENTIMENT_REQ"
echo "========================================"

python3 -m venv "$VENV_DIR"
. "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip

if [ -f "$BASE_REQ" ]; then
    echo
    echo "Installing base requirements..."
    python -m pip install -r "$BASE_REQ"
fi

if [ -f "$SENTIMENT_REQ" ]; then
    echo
    echo "Installing sentiment requirements..."
    python -m pip install -r "$SENTIMENT_REQ"
fi

echo
echo "Verifying core imports..."
python - <<'PY'
import flask
import google.generativeai
import pandas
import plotly
import requests
import dateutil
import xlsxwriter
print("core-imports-ok")
PY

echo
echo "Checking tkinter availability..."
python - <<'PY'
try:
    import tkinter
    print("tkinter-ok")
except Exception as exc:
    print(f"tkinter-missing: {exc}")
    print("Install OS package manually: sudo apt-get update && sudo apt-get install -y python3-tk")
PY

echo
echo "Setup completed."
