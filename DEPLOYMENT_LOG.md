# Deployment Log — SpecimenBase

## Project Overview

- **App:** SpecimenBase — biological specimen dataset repository (Django)
- **Domain:** https://www.stanfordmycomaterials.org
- **Server:** AWS EC2, user `ubuntu`, app at `/srv/specimenbase`
- **Repo:** https://github.com/eisbell82/Django_Trial_Run_eisbell
- **Deploy branch:** `claude/main`

## Deploy Pipeline

Push to `claude/main` triggers two GitHub Actions workflows:

| Workflow | File | Trigger | Purpose |
|----------|------|---------|---------|
| Deploy to AWS | `deploy.yml` | push to `claude/main` | Runs inspect job then deploy job |
| Diagnose Server | `diagnose.yml` | push to `claude/main` or `workflow_dispatch` | Full server health check |

### Deploy job sequence
1. `sudo chown -R ubuntu:www-data /srv/specimenbase` — fix ownership
2. `git fetch` + `git reset --hard origin/claude/main` — pull latest code
3. `deploy/deploy.sh` — pip install, migrate, collectstatic, restart gunicorn + nginx

### Useful URLs
- Live site: https://www.stanfordmycomaterials.org
- Django admin: https://www.stanfordmycomaterials.org/admin/
- GitHub Actions: https://github.com/eisbell82/Django_Trial_Run_eisbell/actions
- Server state snapshot: https://www.stanfordmycomaterials.org/static/inspect.txt

## GitHub Secrets Required

6 secrets must be set in repo Settings → Secrets → Actions:

| Secret | Purpose |
|--------|---------|
| `AWS_HOST` | Server IP or hostname |
| `AWS_USER` | SSH username (`ubuntu`) |
| `AWS_SSH_KEY` | Private SSH key (PEM) for the server |
| `SECRET_KEY` | Django secret key |
| `DATABASE_URL` | PostgreSQL or SQLite connection string |
| `ALLOWED_HOSTS` | Space-separated allowed hostnames |

> To decrypt sensitive operational notes: `openssl enc -aes-256-cbc -d -pbkdf2 -in .secrets.enc -pass pass:'<passphrase>'`

## Incident Log

### 2026-03-16 — Git "dubious ownership" blocking all deploys (runs #195–199+)

**Symptom:** Deploy SSH step failing in 0–1 seconds with no visible output.

**Root cause:** Files inside `/srv/specimenbase/` were owned by `root:root` (from a prior
manual or sudo-based deploy), while the parent directory was `ubuntu:www-data`. Git's
security check blocked all git operations with "detected dubious ownership in repository".

**Fix applied:**
- Added `sudo chown -R ubuntu:www-data /srv/specimenbase` to the **top** of `deploy/deploy.sh`
  (before git fetch — must run first or git refuses to operate)
- Also added to the `deploy.yml` inline script for belt-and-suspenders

**How to detect recurrence:** If deploy fails in <2 seconds, run inspect.yml or check
`/static/inspect.txt` for ownership info. Look for `root:root` on `.git/` or app files.

## Server Notes

- App served by gunicorn (systemd service: `specimenbase`) + nginx
- Static files: `/srv/specimenbase/staticfiles/` → `/static/`
- Media uploads: `/srv/specimenbase/media/` → `/media/`
- SQLite DB: `/srv/specimenbase/db.sqlite3`
- `.env` file lives at `/srv/specimenbase/.env` (not in git — must exist before first deploy)
- ubuntu user has passwordless sudo
- HTTPS is active on the domain (nginx HTTPS config managed outside this repo — likely certbot)
