# SpecimenBase

A curated open repository for biological specimen datasets. Upload, discover, and cite research-grade data with associated provenance records and analysis notebooks.

---

## Using the Site

### No account required

| Page | What it does |
|------|-------------|
| **Home** (`/`) | Browse all datasets. Filter by category, lab, institution, or license. Sort by date, downloads, or title. |
| **Experiments** (`/collections/`) | Same datasets grouped by category (Flame, Mechanical, Chemical, Imaging). |
| **Samples** (`/samples/`) | Cross-dataset sample table. Search, filter, and pick columns from any combination of datasets. |
| **Dataset detail** (`/datasets/<slug>/`) | Full metadata, downloadable files, sample table, and analysis notebooks for a single dataset. |
| **Docs** (`/docs/`) | Quick reference on uploading and licensing. |

### Browsing datasets

Use the search bar to find datasets by title, abstract, or tag. The category chips and sidebar dropdowns narrow results further. Sort controls sit in the top-right of the listing.

### Exploring samples across datasets

The **Samples** page lets you query every sample record regardless of which dataset it belongs to.

1. Use the search bar to match sample IDs, experiment titles, or cell values.
2. Click a category chip (e.g. *Flame*) to restrict to one type — this unlocks the **Columns** picker.
3. Open **Advanced filters** to select which columns to display and to filter by Species, Substrate, or Coating.
4. Click any column header to sort. Click again to reverse. Numeric values sort numerically; text sorts alphabetically; blank / N/A values always sort last.
5. Click **Download CSV** to export exactly what is currently shown (same filters and sort order).

### Downloading dataset files

On a dataset detail page, click the **Download** button next to any file under the *Files* tab. The download counter increments each time.

---

## Contributing

### Creating an account

Click **Sign In → Register** (top right). Accounts are free; no email confirmation is required.

### Uploading a dataset

1. Sign in and click **+ Upload** in the navigation bar.
2. Fill in the required fields:
   - **Title** — concise, descriptive name
   - **Abstract** — what the data contains and how it was collected
   - **Category** — Flame / Mechanical / Chemical / Imaging
   - **License** — see [Licenses](#licenses) below
3. Optionally add metadata: DOI, version, experiment date, lab, institution, tags.
4. Attach a data file (optional but recommended).
5. Attach a Jupyter notebook (optional).
6. Submit — the dataset appears immediately.

### Supported file types

| Type | Extensions |
|------|-----------|
| Tabular data | `.csv`, `.tsv`, `.xlsx` |
| Structured data | `.json` |
| Plain text | `.txt` |
| Imaging | `.tiff`, `.tif` |
| Archives | `.zip` |
| Notebooks | `.ipynb` |
| Max size | 150 MB per file |

### Managing your dataset

From the dataset detail page (while signed in as the owner or an admin):

- **Edit** — update metadata and tags via the edit icon.
- **Add file** — attach additional files under the *Files* tab.
- **Delete file** — remove individual files.
- **Samples tab** — add, edit, or delete individual sample rows; add or rename columns; set units; or bulk-import from a CSV file.
- **Notebook tabs** — add up to 3 analysis notebook tabs per dataset (description, embedded code, Colab/Binder links, or `.ipynb` file).
- **Delete dataset** — permanently removes the dataset and all its files.

### Bulk CSV import for samples

Under the *Samples* tab → **Upload CSV**:

- The first column whose header is `sample_id`, `sample id`, or `id` (case-insensitive) is used as the sample identifier. If none matches, the first column is used.
- All other columns become sample attributes. New columns are created automatically.
- Existing samples are updated; new samples are inserted.

---

## Licenses

| License | Meaning |
|---------|---------|
| **CC BY 4.0** | Free to use with attribution |
| **CC BY-NC 4.0** | Free for non-commercial use with attribution |
| **CC0** | Public domain — no restrictions |
| **Restricted** | Contact the uploader before use |

---

## Running Locally (Development)

Requires Python 3.10 or newer.

```bash
# 1. Clone and set up a virtual environment
git clone https://github.com/eisbell82/Django_Trial_Run_eisbell.git
cd Django_Trial_Run_eisbell
python -m venv .venv && source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Apply migrations and create a superuser
python manage.py migrate
python manage.py createsuperuser

# 4. (Optional) Load demo data
python manage.py seed_demo

# 5. Start the development server
python manage.py runserver
```

Open `http://127.0.0.1:8000/` in your browser.

### Minimum `.env` for development

Create a `.env` file in the project root:

```dotenv
SECRET_KEY=any-random-string-for-local-dev
DEBUG=True
ALLOWED_HOSTS=localhost 127.0.0.1
```

> `ALLOWED_HOSTS` is space-separated (not comma-separated).

---

## Deployment

Deployment is automated via GitHub Actions. Pushing to the `claude/main` branch triggers `deploy.yml`, which SSHes into the server and runs `deploy/deploy.sh`.

### Prerequisites

The following GitHub Secrets must be set in the repository (`Settings → Secrets → Actions`):

| Secret | Value |
|--------|-------|
| `AWS_HOST` | Server IP or hostname |
| `AWS_USER` | SSH username (e.g. `ubuntu`) |
| `AWS_SSH_KEY` | Private SSH key for the server |

### First-time server setup

Before the first deploy, create `/srv/specimenbase/.env` on the server (the deploy script will abort if it is missing):

```bash
sudo cp /srv/specimenbase/.env.example /srv/specimenbase/.env
sudo nano /srv/specimenbase/.env   # fill in SECRET_KEY, ALLOWED_HOSTS, etc.
```

### Deploying

Push to `claude/main` — GitHub Actions handles the rest:

```bash
git push origin claude/main
```

The deploy script will pull the latest code, install dependencies, run migrations, collect static files, and restart gunicorn + nginx.

### Key environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `SECRET_KEY` | *(insecure default)* | Django secret key — **must be changed in production** |
| `DEBUG` | `False` | Set to `True` only in development |
| `ALLOWED_HOSTS` | `localhost 127.0.0.1` | Space-separated list of valid hostnames |
| `DATABASE_URL` | SQLite | PostgreSQL connection string, e.g. `postgres://user:pass@host/db` |
| `GUNICORN_BIND` | `unix:/run/gunicorn/specimenbase.sock` | Socket or TCP address for Gunicorn |
| `GUNICORN_WORKERS` | `2×CPU+1` | Number of worker processes |
| `GUNICORN_LOG_LEVEL` | `info` | Logging verbosity |

### PostgreSQL

Install the extra dependencies and set `DATABASE_URL`:

```bash
pip install psycopg2-binary dj-database-url
```

```dotenv
DATABASE_URL=postgres://specimenbase:password@localhost/specimenbase
```

### Static and media files

- **Static files** are served from `staticfiles/` after running `collectstatic`. Point nginx at this directory for `/static/`.
- **Media files** (uploads) are stored in `media/`. Point nginx at this directory for `/media/`.

---

## Admin

The Django admin interface is available at `/admin/`. Log in with a superuser account to manage all users, datasets, tags, and sample data directly.
