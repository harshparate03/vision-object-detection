#!/usr/bin/env bash
set -euo pipefail

# Bring the runtime database up to date before accepting requests.
python manage.py migrate --noinput
exec gunicorn object_detection.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers 1 --timeout 300 --access-logfile - --error-logfile -
