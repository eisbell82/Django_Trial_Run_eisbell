## Git Rules
- Always work directly on the `claude/main` branch
- Do not create new branches
- Commit and push directly to `claude/main`

## Project Context
- **App:** SpecimenBase — biological specimen dataset repository (Django backend)
- **Domain:** https://www.stanfordmycomaterials.org
- **Server:** AWS EC2, SSH user `ubuntu`, app path `/srv/specimenbase`
- **Repo:** eisbell82/Django_Trial_Run_eisbell

## Deploy System
- Push to `claude/main` triggers `deploy.yml` (GitHub Actions)
- `deploy.yml` runs a single **deploy** job via SSH
- `diagnose.yml` runs full server health check — trigger via `workflow_dispatch` or push
- **6 GitHub secrets required:** `AWS_HOST`, `AWS_USER`, `AWS_SSH_KEY`, `SECRET_KEY`, `DATABASE_URL`, `ALLOWED_HOSTS`
- Cannot use `apt-get` or direct SSH from this sandbox — use GitHub Actions workflows instead
- Sensitive operational notes: decrypt `.secrets.enc` with the session passphrase

## Known Issues & Fixes
- **Git "dubious ownership":** If files in `/srv/specimenbase` are owned by `root:root`, git refuses
  to operate. Fix is `sudo chown -R ubuntu:www-data /srv/specimenbase`. This is now baked into
  `deploy/deploy.sh` (runs automatically at the top of every deploy).
- **Diagnosing deploy failures:** Run `diagnose.yml` via `workflow_dispatch` and inspect the
  Actions log for service status, nginx errors, and disk/memory info.

## Useful Reference URLs
- Live site: https://www.stanfordmycomaterials.org
- Admin panel: https://www.stanfordmycomaterials.org/admin/
- Actions: https://github.com/eisbell82/Django_Trial_Run_eisbell/actions
- Full deployment history: `DEPLOYMENT_LOG.md`
