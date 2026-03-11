#!/usr/bin/env bash
# deploy.sh — Pull latest code and restart services on the AWS server
# Run as the deploy user: bash deploy.sh

set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$APP_DIR/venv"
PYTHON="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"

echo "==> Pulling latest code..."
git -C "$APP_DIR" pull origin claude/django-app-deployment-qvuJi

echo "==> Installing / upgrading dependencies..."
"$PIP" install -q -r "$APP_DIR/requirements.txt"

echo "==> Running migrations..."
"$PYTHON" "$APP_DIR/manage.py" migrate --no-input

echo "==> Collecting static files..."
"$PYTHON" "$APP_DIR/manage.py" collectstatic --no-input --clear

echo "==> Restarting gunicorn..."
sudo systemctl restart specimenbase

echo "==> Reloading nginx..."
sudo nginx -t && sudo systemctl reload nginx

echo "==> Done."
