#!/usr/bin/env bash
# Build Command de Render (producción).
# No ejecutar makemigrations aquí: las 000X_*.py se generan en desarrollo
#   python manage.py makemigrations --settings=config.settings.development
set -euo pipefail
mkdir -p staticfiles
pip install -r requirements.txt
python manage.py collectstatic --noinput --settings=config.settings.production
python manage.py migrate ecommerce --noinput --settings=config.settings.production
python manage.py migrate --noinput --settings=config.settings.production
python manage.py ensure_ecommerce_schema --settings=config.settings.production
python manage.py ensure_jobs_schema --settings=config.settings.production
python manage.py ensure_payments_schema --settings=config.settings.production
python manage.py ensure_sports_schema --settings=config.settings.production
