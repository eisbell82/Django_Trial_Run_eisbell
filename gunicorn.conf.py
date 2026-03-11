# gunicorn.conf.py — Production configuration for SpecimenBase
# Usage: gunicorn -c gunicorn.conf.py specimenbase.wsgi:application

import multiprocessing
import os

# ── Binding ───────────────────────────────────────────────────────────────────
# Bind to a Unix socket (recommended behind nginx) or TCP port
bind = os.environ.get("GUNICORN_BIND", "unix:/run/gunicorn/specimenbase.sock")

# ── Workers ───────────────────────────────────────────────────────────────────
workers = int(os.environ.get("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = "sync"
worker_connections = 1000
timeout = 120
keepalive = 5

# ── Logging ───────────────────────────────────────────────────────────────────
accesslog = "-"       # stdout (systemd/journald captures this)
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# ── Process ───────────────────────────────────────────────────────────────────
proc_name = "specimenbase"
pidfile = "/run/gunicorn/specimenbase.pid"

# ── Preload (optional, saves memory) ─────────────────────────────────────────
preload_app = True
