#!/bin/bash
set -e

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "Listo. Para activar el entorno:"
echo "  source .venv/bin/activate"
echo ""
echo "Luego copia el .env y rellena tus keys:"
echo "  cp .env.example .env"
