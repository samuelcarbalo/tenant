#!/usr/bin/env bash
# Build Command de Render (producción).
# No ejecutar makemigrations aquí: las 000X_*.py se generan en desarrollo
#   python manage.py makemigrations --settings=config.settings.development
set -euo pipefail
pip install -r requirements.txt
python manage.py collectstatic --noinput --settings=config.settings.production
python manage.py migrate --settings=config.settings.production
