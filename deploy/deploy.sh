#!/usr/bin/env bash
# deploy.sh — Pull latest code and restart services on the AWS server
# Run as the deploy user: bash deploy.sh

set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$APP_DIR/venv"
PYTHON="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"

echo "==> Ensuring correct ownership (prevents git dubious-ownership errors)..."
# Files can end up root:root if a previous deploy ran commands as root.
# This must run before git operations or git will refuse to work.
sudo chown -R ubuntu:www-data "$APP_DIR"

echo "==> Pulling latest code..."
git -C "$APP_DIR" fetch origin "${DEPLOY_BRANCH:-claude/main}"
git -C "$APP_DIR" reset --hard "origin/${DEPLOY_BRANCH:-claude/main}"
git -C "$APP_DIR" rev-parse --short HEAD > "$APP_DIR/VERSION"

echo "==> Backing up database and media to S3..."
aws s3 cp "$APP_DIR/db.sqlite3" s3://specimenbase-backups-318270726326-us-east-1-an/db.sqlite3 || true
aws s3 sync "$APP_DIR/media/" s3://specimenbase-backups-318270726326-us-east-1-an/media/ || true

echo "==> Checking .env exists..."
if [ ! -f "$APP_DIR/.env" ]; then
    echo "ERROR: $APP_DIR/.env not found. Create it from .env.example before deploying." >&2
    exit 1
fi

echo "==> Ensuring Python virtualenv exists..."
if [ ! -f "$VENV_DIR/bin/python" ]; then
    python3 -m venv "$VENV_DIR"
fi

echo "==> Fixing file permissions..."
# Directory must be group-writable by www-data for SQLite WAL files
sudo chown ubuntu:www-data "$APP_DIR"
sudo chmod 775 "$APP_DIR"
# DB file: ubuntu owns it (for migrations), www-data group can write (for gunicorn)
sudo chown ubuntu:www-data "$APP_DIR/db.sqlite3" 2>/dev/null || true
sudo chmod 664 "$APP_DIR/db.sqlite3" 2>/dev/null || true
mkdir -p "$APP_DIR/media"
sudo chown -R www-data:www-data "$APP_DIR/media"
mkdir -p "$APP_DIR/staticfiles"

echo "==> Installing / upgrading dependencies..."
"$PIP" install -q -r "$APP_DIR/requirements.txt"

echo "==> Running migrations..."
"$PYTHON" "$APP_DIR/manage.py" migrate --no-input
# Fix permissions on WAL/SHM files created by migrate so gunicorn can write them
sudo chown ubuntu:www-data "$APP_DIR"/db.sqlite3* 2>/dev/null || true
sudo chmod 664 "$APP_DIR"/db.sqlite3* 2>/dev/null || true

echo "==> Collecting static files..."
"$PYTHON" "$APP_DIR/manage.py" collectstatic --no-input --clear

echo "==> Installing systemd service unit..."
sudo cp "$APP_DIR/deploy/specimenbase.service" /etc/systemd/system/specimenbase.service
sudo systemctl daemon-reload
sudo systemctl enable specimenbase

echo "==> Restarting gunicorn..."
sudo systemctl restart specimenbase

echo "==> Ensuring SSL certificate..."
CERT=/etc/letsencrypt/live/stanfordmycomaterials.org/fullchain.pem
if [ ! -f "$CERT" ]; then
    sudo apt-get install -y -q certbot python3-certbot-nginx
    sudo certbot --nginx -d stanfordmycomaterials.org \
        --non-interactive --agree-tos \
        -m admin@stanfordmycomaterials.org
fi

echo "==> Updating nginx config..."
sudo cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/specimenbase
sudo ln -sf /etc/nginx/sites-available/specimenbase /etc/nginx/sites-enabled/specimenbase

echo "==> Reloading nginx..."
sudo nginx -t && sudo systemctl reload nginx

echo "==> Cleaning up stale artifacts..."
rm -f "$APP_DIR/staticfiles/inspect.txt"

echo "==> Done."
