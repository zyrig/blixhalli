#!/usr/bin/env bash
# Køyrer på Render kvar gong ein ny versjon blir lagd ut.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py seed_if_empty
python manage.py ensure_admin
