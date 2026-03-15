"""
Build a paginated static HTML dashboard from the mechanical_analysis notebooks.

Usage
-----
    python build_dashboard.py                          # uses default paths
    python build_dashboard.py --data /path/to/input_data
    python build_dashboard.py --data /path/to/input_data --repo /path/to/repo --out /path/to/docs

Google Drive example (macOS/Linux with Drive mounted):
    python build_dashboard.py --data "/Volumes/GoogleDrive/My Drive/mechanical_analysis/input_data"

Output
------
    docs/
        index.html           – bulk overview + summary tables + group nav cards
        groups/
            <group>.html     – per-group: overlay SVGs + all specimens in that group
"""

import argparse, os, sys, io, base64, warnings, re
warnings.filterwarnings("ignore")

# ── CLI args ─────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--repo", default=os.path.dirname(os.path.abspath(__file__)),
                    help="Repository root (contains custom_python_functions/)")
parser.add_argument("--data", default=None,
                    help="Path to input_data folder (default: <repo>/input_data)")
parser.add_argument("--out",  default=None,
                    help="Output docs folder   (default: <repo>/docs)")
args = parser.parse_args()

REPO     = args.repo
PY_ROOT  = os.path.join(REPO, "custom_python_functions")
DATA_DIR = args.data  or os.path.join(REPO, "input_data")
OUT_DIR  = args.out   or os.path.join(REPO, "docs")

os.makedirs(os.path.join(OUT_DIR, "groups"), exist_ok=True)

print(f"REPO     : {REPO}")
print(f"DATA_DIR : {DATA_DIR}")
print(f"OUT_DIR  : {OUT_DIR}")

if PY_ROOT not in sys.path:
    sys.path.insert(0, PY_ROOT)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

# ── Load custom modules ───────────────────────────────────────────────────────
from Utility.csv_file_browser import force_fresh_import

def load(alias, module_name, fname):
    try:
        return force_fresh_import(module_name, os.path.join(PY_ROOT, fname))
    except Exception as e:
        print(f"❌ {alias}: {e}"); return None

sp   = load("sp",   "Plotting.Single_Plot",       "Plotting/Single_Plot.py")
mult = load("mult", "Plotting.Multi_Plot",        "Plotting/Multi_Plot.py")
pp   = load("pp",   "Plotting.Polyfit_Processor", "Plotting/Polyfit_Processor.py")
mp   = load("mp",   "Plotting.Max_Processor",     "Plotting/Max_Processor.py")
cb   = load("cb",   "Utility.csv_file_browser",   "Utility/csv_file_browser.py")
moe  = load("moe",  "Plotting.MOE_Processor",     "Plotting/MOE_Processor.py")
print("✅ Modules loaded")

# ── Helpers ───────────────────────────────────────────────────────────────────
def fig_to_b64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="svg", bbox_inches="tight")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()

def svg_to_b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def slugify(name):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)

# Shared CSS/JS injected into every page
SHARED_CSS = """
<style>
:root{--bg:#0f1117;--surface:#1a1d27;--border:#2a2d3a;--text:#e8e8e8;--muted:#888;--accent:#c0392b}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'DM Mono','Courier New',monospace;font-size:13px}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
header{background:var(--surface);border-bottom:1px solid var(--border);padding:1.25rem 2rem;display:flex;align-items:baseline;gap:1.5rem}
header h1{font-size:18px;font-weight:600;letter-spacing:.04em;white-space:nowrap}
header .breadcrumb{color:var(--muted);font-size:11px}
header .breadcrumb a{color:var(--muted)}header .breadcrumb a:hover{color:var(--accent)}
main{padding:2rem;max-width:1400px;margin:0 auto}
section{margin-bottom:3rem}
section h2{font-size:13px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);
           border-bottom:1px solid var(--border);padding-bottom:.5rem;margin-bottom:1.25rem}
section h3{font-size:12px;color:var(--muted);margin:1.25rem 0 .6rem}
.grid-2{display:grid;grid-template-columns:repeat(auto-fill,minmax(480px,1fr));gap:1.25rem}
.grid-3{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:1rem}
.fig-wrap{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:.75rem}
.fig-name{font-size:11px;color:var(--muted);margin-bottom:.5rem}
.fig-wrap img{width:100%;height:auto;display:block}
.summary-table{width:100%;border-collapse:collapse;font-size:12px}
.summary-table th{background:var(--border);padding:7px 12px;text-align:left;font-weight:600}
.summary-table td{padding:7px 12px;border-bottom:1px solid var(--border)}
.summary-table tr:last-child td{border-bottom:none}
.group-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:1rem;margin-top:1rem}
.group-card{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:1rem;
            display:flex;flex-direction:column;gap:.4rem}
.group-card .name{font-size:12px;font-weight:600}
.group-card .meta{font-size:11px;color:var(--muted)}
.group-card a.btn{margin-top:.5rem;text-align:center;background:var(--border);border-radius:4px;
                  padding:5px 10px;font-size:11px;color:var(--text);text-transform:uppercase;letter-spacing:.06em}
.group-card a.btn:hover{background:var(--accent);text-decoration:none;color:#fff}
.muted{color:var(--muted)}
</style>"""

# ── 1. Batch-process ─────────────────────────────────────────────────────────
print("\n📊 Batch processing strength metrics…")
df_strength = mp.batch_process_folder(DATA_DIR, overwrite_cache=False)
print(f"   {len(df_strength)} specimens")

print("📊 Batch processing MOE metrics…")
df_moe = moe.batch_process_folder(DATA_DIR, fit_range=5, scan_min=0,
                                   scan_max=8, best_window=True, overwrite_cache=False)
print(f"   {len(df_moe)} specimens")

groups = sorted(df_strength["Specimen Group"].unique())
print(f"   {len(groups)} groups: {', '.join(groups)}")

# ── 2. Summary tables ─────────────────────────────────────────────────────────
strength_cols = [c for c in df_strength.columns
                 if any(k in c for k in ["Yield Stress","Inflection"])]
moe_cols      = [c for c in df_moe.columns
                 if any(k in c for k in ["Elastic Modulus","Modulus"])]

def group_summary_html(df, value_cols):
    grp  = df.groupby("Specimen Group")[value_cols]
    mean = grp.mean().round(3)
    std  = grp.std().round(3)
    rows = []
    for g in mean.index:
        row = {"Group": g}
        for c in value_cols:
            row[c] = f"{mean.loc[g,c]:.3f} ± {std.loc[g,c]:.3f}"
        rows.append(row)
    return pd.DataFrame(rows).to_html(index=False, classes="summary-table", border=0)

# Per-group specimen counts and stats for group cards
group_stats = {}
for g in groups:
    n = (df_strength["Specimen Group"] == g).sum()
    ys_col = next((c for c in strength_cols if "Yield Stress" in c and "(y)" in c), None)
    m_col  = next((c for c in moe_cols if "Elastic Modulus" in c), None)
    ys = df_strength.loc[df_strength["Specimen Group"] == g, ys_col].dropna() if ys_col else pd.Series()
    me = df_moe.loc[df_moe["Specimen Group"] == g, m_col].dropna() if m_col else pd.Series()
    group_stats[g] = {
        "n": n,
        "ys_mean": f"{ys.mean():.2f}" if len(ys) else "—",
        "moe_mean": f"{me.mean():.2f}" if len(me) else "—",
    }

# ── 3. Bulk overview figure ───────────────────────────────────────────────────
print("\n📈 Generating bulk overview figure…")
try:
    n_groups = len(groups)
    colors = plt.cm.tab20(np.linspace(0, 1, n_groups)) if n_groups > 10 else plt.cm.tab10(np.linspace(0, 1, n_groups))
    fig, ax1 = plt.subplots(figsize=(max(8, n_groups * 1.2), 5))
    plt.style.use("fivethirtyeight")
    ax2 = ax1.twinx()

    ys_col  = next((c for c in strength_cols if "Yield Stress" in c and "(y)" in c), None)
    moe_col = next((c for c in moe_cols if "Elastic Modulus" in c), None)
    xs = np.arange(n_groups)
    w  = 0.3

    for i, g in enumerate(groups):
        c = colors[i]
        if ys_col:
            vals = df_strength.loc[df_strength["Specimen Group"] == g, ys_col].dropna()
            if len(vals):
                ax1.errorbar(i - w/2, vals.mean(), yerr=vals.std() if len(vals)>1 else 0,
                             fmt="o", color=c, capsize=4, ms=7, label=g)
        if moe_col:
            vals = df_moe.loc[df_moe["Specimen Group"] == g, moe_col].dropna()
            if len(vals):
                ax2.errorbar(i + w/2, vals.mean(), yerr=vals.std() if len(vals)>1 else 0,
                             fmt="s", color=c, capsize=4, ms=7, alpha=0.75)

    ax1.set_xticks(xs)
    ax1.set_xticklabels(groups, rotation=35, ha="right", fontsize=max(6, 10 - n_groups//5))
    ax1.set_ylabel("Yield Stress (MPa)", fontsize=10)
    ax2.set_ylabel("Elastic Modulus (MPa)", fontsize=10)
    ax1.set_title("Strength (●) & MOE (■) by Specimen Group — mean ± std", fontsize=11)
    fig.tight_layout()
    bulk_b64 = fig_to_b64(fig)
    plt.close(fig)
    print("   ✅ bulk overview done")
except Exception as e:
    print(f"   ⚠️  bulk overview failed: {e}")
    bulk_b64 = None

# ── 4. Generate all SVGs ──────────────────────────────────────────────────────
tmp_strength = os.path.join(OUT_DIR, "_tmp_group_strength")
tmp_moe      = os.path.join(OUT_DIR, "_tmp_group_moe")
tmp_sp_s     = os.path.join(OUT_DIR, "_tmp_spec_strength")
tmp_sp_m     = os.path.join(OUT_DIR, "_tmp_spec_moe")
for d in [tmp_strength, tmp_moe, tmp_sp_s, tmp_sp_m]:
    os.makedirs(d, exist_ok=True)

print("\n📈 Exporting per-group strength SVGs…")
try:
    sp.export_groups_strength_svg(DATA_DIR, output_folder=tmp_strength)
    print("   ✅")
except Exception as e: print(f"   ⚠️  {e}")

print("📈 Exporting per-group MOE SVGs…")
try:
    moe.export_groups_moe_svg(DATA_DIR, output_folder=tmp_moe,
                               best_window=True, fit_range=5, scan_min=0, scan_max=8, xlim=(0,25))
    print("   ✅")
except Exception as e: print(f"   ⚠️  {e}")

print("📈 Exporting per-specimen strength SVGs…")
try:
    sp.export_all_strength_svg(DATA_DIR, output_folder=tmp_sp_s, xlim=None, ylim=None)
    print("   ✅")
except Exception as e: print(f"   ⚠️  {e}")

print("📈 Exporting per-specimen MOE SVGs…")
try:
    moe.export_all_moe_svg(DATA_DIR, output_folder=tmp_sp_m,
                            best_window=True, fit_range=5, scan_min=0, scan_max=8, xlim=(0,25))
    print("   ✅")
except Exception as e: print(f"   ⚠️  {e}")

# ── 5. Index SVG files by group ───────────────────────────────────────────────
def svgs_in(directory):
    if not os.path.isdir(directory): return {}
    return {f[:-4]: os.path.join(directory, f)
            for f in sorted(os.listdir(directory)) if f.endswith(".svg")}

group_strength_paths = svgs_in(tmp_strength)
group_moe_paths      = svgs_in(tmp_moe)
spec_strength_paths  = svgs_in(tmp_sp_s)
spec_moe_paths       = svgs_in(tmp_sp_m)

def specimens_for_group(group, spec_dict):
    """Return {name: path} for specimens belonging to this group."""
    # Specimen SVG names follow <group>_<n>_<type> or <group_slug>_<n>_<type>
    slug = slugify(group)
    return {k: v for k, v in spec_dict.items()
            if k.startswith(group) or k.startswith(slug)}

# ── 6. Build per-group pages ──────────────────────────────────────────────────
print("\n🌐 Building per-group pages…")

def svg_panel(name, path):
    b64 = svg_to_b64(path)
    return (f'<div class="fig-wrap">'
            f'<div class="fig-name">{name}</div>'
            f'<img src="data:image/svg+xml;base64,{b64}" loading="lazy">'
            f'</div>')

for g in groups:
    slug = slugify(g)
    gs_path  = group_strength_paths.get(f"{g}_strength") or group_strength_paths.get(f"{slug}_strength")
    gm_path  = group_moe_paths.get(f"{g}_moe")           or group_moe_paths.get(f"{slug}_moe")
    sp_s     = specimens_for_group(g, spec_strength_paths)
    sp_m     = specimens_for_group(g, spec_moe_paths)

    overlay_section = ""
    if gs_path or gm_path:
        panels = ""
        if gs_path: panels += svg_panel("Strength overlay — all specimens", gs_path)
        if gm_path: panels += svg_panel("MOE overlay — all specimens",      gm_path)
        overlay_section = f'<section><h2>Group Overlays</h2><div class="grid-2">{panels}</div></section>'

    def specimen_grid(d, label):
        if not d: return ""
        panels = "".join(svg_panel(k, v) for k, v in sorted(d.items()))
        return f'<section><h2>{label}</h2><div class="grid-3">{panels}</div></section>'

    ys_col  = next((c for c in strength_cols if "Yield Stress" in c and "(y)" in c), None)
    m_col   = next((c for c in moe_cols if "Elastic Modulus" in c), None)
    st = group_stats[g]
    meta_html = (f'<p class="muted" style="font-size:11px;margin-bottom:1.5rem">'
                 f'{st["n"]} specimens &nbsp;·&nbsp; '
                 f'Yield Stress {st["ys_mean"]} MPa avg &nbsp;·&nbsp; '
                 f'MOE {st["moe_mean"]} MPa avg</p>')

    page = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{g} — Mechanical Analysis</title>
{SHARED_CSS}
</head><body>
<header>
  <h1>// {g}</h1>
  <span class="breadcrumb"><a href="../index.html">← Overview</a></span>
</header>
<main>
{meta_html}
{overlay_section}
{specimen_grid(sp_s, "Specimen Strength Curves")}
{specimen_grid(sp_m, "Specimen MOE Curves")}
</main>
</body></html>"""

    page_path = os.path.join(OUT_DIR, "groups", f"{slug}.html")
    with open(page_path, "w") as f:
        f.write(page)
    size_kb = os.path.getsize(page_path) // 1024
    print(f"   {g}: {size_kb} KB  ({len(sp_s)} strength + {len(sp_m)} MOE specimens)")

# ── 7. Build index.html ───────────────────────────────────────────────────────
print("\n🌐 Building index.html…")

bulk_fig = ""
if bulk_b64:
    bulk_fig = (f'<section><h2>Bulk Overview — Strength &amp; MOE by Group</h2>'
                f'<img src="data:image/svg+xml;base64,{bulk_b64}" '
                f'style="width:100%;max-width:1100px;height:auto;display:block;margin:0 auto">'
                f'</section>')

table_section = ""
if strength_cols or moe_cols:
    table_section = "<section><h2>Summary Statistics</h2>"
    if strength_cols:
        table_section += f"<h3>Strength</h3>{group_summary_html(df_strength, strength_cols)}"
    if moe_cols:
        table_section += f"<h3>Elastic Modulus</h3>{group_summary_html(df_moe, moe_cols)}"
    table_section += "</section>"

cards_html = ""
for g in groups:
    slug = slugify(g)
    st = group_stats[g]
    cards_html += (f'<div class="group-card">'
                   f'<div class="name">{g}</div>'
                   f'<div class="meta">{st["n"]} specimens</div>'
                   f'<div class="meta">YS: {st["ys_mean"]} MPa</div>'
                   f'<div class="meta">MOE: {st["moe_mean"]} MPa</div>'
                   f'<a class="btn" href="groups/{slug}.html">View →</a>'
                   f'</div>')

index = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mechanical Analysis Dashboard</title>
{SHARED_CSS}
</head><body>
<header>
  <h1>// Mechanical Compression Analysis</h1>
  <span class="breadcrumb" style="color:var(--muted);font-size:11px">
    Perez et al. 2025 — Mycotecture Phase II &nbsp;·&nbsp; {len(groups)} groups &nbsp;·&nbsp; {len(df_strength)} specimens
  </span>
</header>
<main>

{bulk_fig}

<section>
  <h2>Specimen Groups</h2>
  <div class="group-cards">{cards_html}</div>
</section>

{table_section}

</main>
</body></html>"""

index_path = os.path.join(OUT_DIR, "index.html")
with open(index_path, "w") as f:
    f.write(index)
print(f"   index.html: {os.path.getsize(index_path)//1024} KB")

# ── 8. Remove temp SVG folders ────────────────────────────────────────────────
import shutil
for d in [tmp_strength, tmp_moe, tmp_sp_s, tmp_sp_m]:
    shutil.rmtree(d, ignore_errors=True)

# ── 9. Zip the docs/ folder ───────────────────────────────────────────────────
import zipfile
zip_path = os.path.join(os.path.dirname(OUT_DIR), "mechanical_analysis_dashboard.zip")
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(OUT_DIR):
        for fname in files:
            abs_path = os.path.join(root, fname)
            arc_path = os.path.relpath(abs_path, os.path.dirname(OUT_DIR))
            zf.write(abs_path, arc_path)

total_kb = os.path.getsize(zip_path) // 1024
print(f"\n📦 Dashboard zip: {zip_path} ({total_kb} KB)")
print("🎉 Done.")
