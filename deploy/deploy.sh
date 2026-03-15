#!/usr/bin/env bash
# deploy.sh — Pull latest code and restart services on the AWS server
# Run as the deploy user: bash deploy.sh

set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$APP_DIR/venv"
PYTHON="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"

echo "==> Pulling latest code..."
git -C "$APP_DIR" fetch origin "${DEPLOY_BRANCH:-main}"
git -C "$APP_DIR" reset --hard "origin/${DEPLOY_BRANCH:-main}"
git -C "$APP_DIR" rev-parse --short HEAD > "$APP_DIR/VERSION"

echo "==> Fixing file permissions..."
# Directory must be group-writable by www-data for SQLite WAL files
sudo chown ubuntu:www-data "$APP_DIR"
sudo chmod 775 "$APP_DIR"
# DB file: ubuntu owns it (for migrations), www-data group can write (for gunicorn)
sudo chown ubuntu:www-data "$APP_DIR/db.sqlite3" 2>/dev/null || true
sudo chmod 664 "$APP_DIR/db.sqlite3" 2>/dev/null || true
mkdir -p "$APP_DIR/media"
sudo chown -R www-data:www-data "$APP_DIR/media"

echo "==> Installing / upgrading dependencies..."
"$PIP" install -q -r "$APP_DIR/requirements.txt"

echo "==> Running migrations..."
"$PYTHON" "$APP_DIR/manage.py" migrate --no-input

echo "==> Collecting static files..."
"$PYTHON" "$APP_DIR/manage.py" collectstatic --no-input --clear

echo "==> Installing systemd service unit..."
sudo cp "$APP_DIR/deploy/specimenbase.service" /etc/systemd/system/specimenbase.service
sudo systemctl daemon-reload
sudo systemctl enable specimenbase

echo "==> Restarting gunicorn..."
sudo systemctl restart specimenbase

echo "==> Updating nginx config..."
sudo cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/specimenbase
sudo ln -sf /etc/nginx/sites-available/specimenbase /etc/nginx/sites-enabled/specimenbase

echo "==> Reloading nginx..."
sudo nginx -t && sudo systemctl reload nginx

echo "==> Done."
