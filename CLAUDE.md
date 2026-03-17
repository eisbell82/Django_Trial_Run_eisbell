## Git Rules
- Always work directly on the `claude/main` branch
- Do not create new branches
- Commit and push directly to `claude/main`

## Project Context
- **App:** SpecimenBase — biological specimen dataset repository (Django backend)
- **Domain:** https://www.stanfordmycomaterials.org (HTTPS via Let's Encrypt / certbot)
- **Server:** AWS EC2, SSH user `ubuntu`, app path `/srv/specimenbase`
- **Repo:** eisbell82/Django_Trial_Run_eisbell
- **DB:** SQLite at `/srv/specimenbase/db.sqlite3`
- **Media:** `/srv/specimenbase/media/` (uploaded files, sample photos)
- **Static:** `/srv/specimenbase/staticfiles/`
- **App server:** gunicorn (systemd service: `specimenbase`) + nginx

## Deploy System
- Push to `claude/main` triggers `deploy.yml` (GitHub Actions)
- `deploy.yml` runs a single **deploy** job via SSH
- `diagnose.yml` runs full server health check — trigger via `workflow_dispatch` or push
- **6 GitHub secrets required:** `AWS_HOST`, `AWS_USER`, `AWS_SSH_KEY`, `SECRET_KEY`, `DATABASE_URL`, `ALLOWED_HOSTS`
- Cannot use `apt-get` or direct SSH from this sandbox — use GitHub Actions workflows instead
- Deploy script (`deploy/deploy.sh`) runs: chown fix → git pull → pip install → migrate → collectstatic → restart gunicorn/nginx
- certbot step in deploy.sh auto-issues SSL cert on first deploy (requires A record pointing to EC2 IP)

## S3 Backups
- Bucket: `s3://specimenbase-backups` (versioning enabled)
- IAM role `Bucket_Access` attached to EC2 instance (no credentials in code)
- deploy.sh backs up `db.sqlite3` and `media/` to S3 before each deploy
- View backups: AWS Console → S3 → specimenbase-backups

## Data Model Overview
All models live in `repository/models.py`. Key models:
- **Dataset** — a published experiment dataset; has `image` (overview photo), `is_private`, `allowed_users`, `tags`, `slug`
- **SampleColumn** — a column definition for a dataset's sample table; has `group` field: `'characteristics'` (text-dominant) or `'data'` (numeric-dominant)
- **Sample** — a single specimen row in a dataset
- **SampleValue** — the value for a (sample, column) pair
- **SamplePhoto** — one of potentially many photos per sample (ForeignKey to Sample, `related_name='photos'`)
- **DataFile** — a file attachment on a Dataset
- **Notebook** — a code/dashboard tab on a Dataset
- **Tag, AboutPage, AboutPhoto, TodoItem** — supporting models

## Key Features Built
- **Dataset samples tab** (detail page): two column group toggles (Characteristics / Data), sortable column headers, 25/50/100 per-page, pagination
- **Sample photos**: multiple photos per sample via SamplePhoto model; crop/rotate editor popup (Cropper.js, lazy-loaded); lightbox viewer with prev/next navigation and keyboard arrows; "N photos" tab button inline with sample ID
- **CSV upload auto-detection**: columns with >50% numeric values → 'data' group; otherwise → 'characteristics'. Manual override via group dropdown in edit mode.
- **Global samples page** (`/samples/`): column value text filter in advanced filters (pick column + contains text); persists across column sort clicks
- **HTTPS**: nginx serves HTTPS on port 443; HTTP redirects to HTTPS; certbot auto-provisions cert on first deploy

## Known Issues & Fixes
- **Git "dubious ownership":** If files in `/srv/specimenbase` are owned by `root:root`, git refuses
  to operate. Fix is `sudo chown -R ubuntu:www-data /srv/specimenbase`. This is now baked into
  `deploy/deploy.sh` (runs automatically at the top of every deploy).
- **Diagnosing deploy failures:** Run `diagnose.yml` via `workflow_dispatch` and inspect the
  Actions log for service status, nginx errors, and disk/memory info.
- **EC2 instance replaced:** If the server is replaced, run `python manage.py createsuperuser`
  via SSH or a one-off Actions workflow. S3 backups allow restoring db.sqlite3 and media/.

## Useful Reference URLs
- Live site: https://www.stanfordmycomaterials.org
- Admin panel: https://www.stanfordmycomaterials.org/admin/
- Actions: https://github.com/eisbell82/Django_Trial_Run_eisbell/actions
- Full deployment history: `DEPLOYMENT_LOG.md`
