#!/usr/bin/env bash
# Render build script
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --noinput

# Show which database we're connecting to (helps debug)
echo "Running migrations..."
python manage.py showmigrations
python manage.py migrate --noinput --run-syncdb
echo "Migrations done."
