from django.db import migrations, models


OVERVIEW_SECTIONS = [
    {
        "heading": "Getting Started",
        "body": "",
        "rows": (
            "Browse experiments | No account required\n"
            "Download files | No account required\n"
            "Upload experiments | Account required\n"
            "Manage experiments | Admin access required"
        ),
        "is_list": False,
        "order": 0,
    },
    {
        "heading": "Uploading an Experiment",
        "body": "",
        "rows": (
            "Create an account or sign in\n"
            "Click + Upload in the navigation bar\n"
            "Fill in the experiment title, abstract, category, and license\n"
            "Attach your data file (CSV, XLSX, JSON, ZIP \u2014 max 150 MB)\n"
            "Optionally attach an analysis notebook (.ipynb)\n"
            "Submit \u2014 your experiment will appear immediately"
        ),
        "is_list": True,
        "order": 1,
    },
    {
        "heading": "Sample Records",
        "body": (
            "Each experiment can have a structured sample table. "
            "Columns are grouped as Sample characteristics (descriptive fields) "
            "or Sample data (numeric measurements). Samples can be added manually, "
            "imported via CSV, or browsed globally across all experiments from the Samples tab."
        ),
        "rows": (
            "Add samples | Manually or via CSV upload\n"
            "Sample photos | Multiple images per sample\n"
            "Global search | Filter across all experiments"
        ),
        "is_list": False,
        "order": 2,
    },
    {
        "heading": "Supported File Types",
        "body": "",
        "rows": (
            "Tabular data | CSV, TSV, XLSX\n"
            "Structured data | JSON\n"
            "Archives | ZIP\n"
            "Notebooks | .ipynb (Jupyter)\n"
            "Images | JPG, PNG, WebP, TIFF, SVG, HEIC and more\n"
            "Max file size | 150 MB per file"
        ),
        "is_list": False,
        "order": 3,
    },
    {
        "heading": "Licenses",
        "body": "",
        "rows": (
            "CC BY 4.0 | Attribution required\n"
            "CC BY-NC 4.0 | Non-commercial only\n"
            "CC0 | Public domain\n"
            "Restricted | Contact uploader"
        ),
        "is_list": False,
        "order": 4,
    },
]

NAMING_SECTIONS = [
    {
        "heading": "Sample ID",
        "body": (
            "Every sample requires a unique Sample ID within its experiment. "
            "IDs should be short, human-readable, and consistent across an experiment."
        ),
        "rows": (
            "Recommended format | Alphanumeric, no spaces (e.g. S-01, MYC-003)\n"
            "Case | Use a consistent case \u2014 mixed case is allowed\n"
            "Uniqueness | Must be unique within an experiment"
        ),
        "is_list": False,
        "order": 0,
    },
    {
        "heading": "Column Names",
        "body": (
            "Column names define the fields in the sample table. "
            "Use clear, descriptive names so that samples are interpretable across experiments."
        ),
        "rows": (
            "Format | Title case preferred (e.g. Substrate Type, Tensile Strength)\n"
            "Units | Include units in brackets (e.g. Mass [g], Temperature [\u00b0C])\n"
            "Reserved names | Sample ID and Type are built-in \u2014 do not use as column names"
        ),
        "is_list": False,
        "order": 1,
    },
    {
        "heading": "Column Groups",
        "body": "Every column belongs to one of two groups, which controls where it appears in the sample table.",
        "rows": (
            "Characteristics | Descriptive / categorical fields (species, substrate, treatment, etc.)\n"
            "Data | Numeric measurements (mass, strength, conductivity, etc.)\n"
            "Auto-detection | CSV import assigns groups based on >50% numeric values\n"
            "Override | Group can be changed manually via the column edit dropdown"
        ),
        "is_list": False,
        "order": 2,
    },
    {
        "heading": "CSV Structure",
        "body": "When importing samples via CSV, the file must follow this structure:",
        "rows": (
            "First row | Header row with column names\n"
            "Sample ID column | Must be named Sample ID (case-insensitive)\n"
            "Type column | Optional \u2014 maps to the built-in Type field\n"
            "Additional columns | Any number of characteristic or data columns\n"
            "Empty cells | Allowed \u2014 recorded as blank values\n"
            "Encoding | UTF-8 recommended"
        ),
        "is_list": False,
        "order": 3,
    },
    {
        "heading": "Experiment Metadata",
        "body": "",
        "rows": (
            "Title | Descriptive, unique name for the experiment\n"
            "Abstract | Short summary of the experiment's purpose and methods\n"
            "Category | Broad material or research category used for global filtering\n"
            "Tags | Free-form keywords for discovery (comma-separated)\n"
            "License | Controls how others may reuse the data"
        ),
        "is_list": False,
        "order": 4,
    },
]


def seed_sections(apps, schema_editor):
    DocsSection = apps.get_model('repository', 'DocsSection')
    if DocsSection.objects.exists():
        return
    for data in OVERVIEW_SECTIONS:
        DocsSection.objects.create(tab='overview', **data)
    for data in NAMING_SECTIONS:
        DocsSection.objects.create(tab='naming', **data)


def unseed_sections(apps, schema_editor):
    apps.get_model('repository', 'DocsSection').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('repository', '0018_add_dataset_photo'),
    ]

    operations = [
        migrations.CreateModel(
            name='DocsSection',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tab', models.CharField(
                    choices=[('overview', 'Overview'), ('naming', 'Naming Conventions')],
                    default='overview', max_length=20)),
                ('heading', models.CharField(max_length=200)),
                ('body', models.TextField(blank=True,
                    help_text='Optional paragraph text. Blank lines = new paragraph.')),
                ('rows', models.TextField(blank=True,
                    help_text="One row per line. Info block: 'Key | Value'. List items: just the text.")),
                ('is_list', models.BooleanField(default=False,
                    help_text='Render rows as ordered list instead of info block.')),
                ('order', models.PositiveIntegerField(default=0)),
            ],
            options={'ordering': ['tab', 'order', 'pk']},
        ),
        migrations.RunPython(seed_sections, unseed_sections),
    ]
