"""
Management command: python manage.py seed_demo

Seeds the database with the five demo datasets from the original HTML mockup
so the app looks populated on first run.
"""

from django.core.management.base import BaseCommand
from repository.models import Dataset, Tag, Notebook


DATASETS = [
    {
        "title": "ERS_F Forelimb Morphometrics — Adult Cohort 2024",
        "abstract": (
            "Morphometric measurements collected from adult ERS_F specimens (n=84) across "
            "forelimb skeletal elements including humerus, radius, ulna, and associated "
            "cartilage. Data collected via digital calipers and photogrammetric landmark "
            "digitisation. Associated curve analysis and modulus data included for each "
            "specimen. All raw CSVs, analysis outputs, and metadata provided."
        ),
        "category": "morphology",
        "license": "cc_by_4",
        "doi": "10.9999/sb.2024.0041",
        "version": "v3",
        "species": "ERS_F",
        "specimen_count": 84,
        "anatomical_region": "Forelimb",
        "lab": "Dsenesky Lab",
        "institution": "Stanford University",
        "file_size_display": "14.2 MB",
        "download_count": 142,
        "tags": [("rodent", "default"), ("forelimb", "default"), ("skeletal", "default"), ("adult", "default"), ("csv", "default")],
        "notebooks": [
            {
                "filename": "forelimb_analysis.ipynb",
                "description": (
                    "Loads raw CSV measurements, performs QC filtering, computes summary "
                    "statistics per element, and generates publication-ready figures."
                ),
            }
        ],
    },
    {
        "title": "ERS_W1 Hindlimb Skeletal Measurements — Wild Series",
        "abstract": (
            "CT-scan derived skeletal measurements of hindlimb elements from wild-caught "
            "ERS_W1 specimens. Includes femur, tibia, and fibula length, cortical thickness, "
            "and trabecular bone volume fraction. Raw DICOM exports and processed XLSX "
            "summary tables provided."
        ),
        "category": "ct_mri",
        "license": "cc_by_4",
        "doi": "10.9999/sb.2024.0038",
        "version": "v1",
        "species": "ERS_W1",
        "specimen_count": 62,
        "anatomical_region": "Hindlimb",
        "lab": "Dsenesky Lab",
        "institution": "Stanford University",
        "file_size_display": "218.4 MB",
        "download_count": 87,
        "tags": [("rodent", "default"), ("hindlimb", "default"), ("ct scan", "blue"), ("xlsx", "default")],
        "notebooks": [
            {
                "filename": "hindlimb_ct_summary.ipynb",
                "description": "Processes DICOM exports and generates cross-sectional area plots.",
            }
        ],
    },
    {
        "title": "GL_F Cranial Landmark Coordinates — Geometric Morphometrics",
        "abstract": (
            "Three-dimensional landmark coordinates digitised from GL_F cranial specimens "
            "using Mimics and landmark editor software. Dataset includes 42 landmarks per "
            "specimen across 56 individuals. Procrustes-aligned coordinates and consensus "
            "configuration provided."
        ),
        "category": "morphology",
        "license": "cc_by_nc_4",
        "doi": "10.9999/sb.2024.0031",
        "version": "v2",
        "species": "GL_F",
        "specimen_count": 56,
        "anatomical_region": "Cranium",
        "lab": "Dsenesky Lab",
        "institution": "Stanford University",
        "file_size_display": "3.1 MB",
        "download_count": 203,
        "tags": [("cranium", "default"), ("landmarks", "default"), ("geometric morphometrics", "default"), ("csv", "default")],
        "notebooks": [],
    },
    {
        "title": "Po_F Postcranial Skeletal Series — Peromyscus",
        "abstract": (
            "High-resolution histology and postcranial skeletal measurements from Peromyscus "
            "specimens. TIFF stacks at 10 µm resolution alongside CSV morphometric tables. "
            "Covers vertebral column, pelvis, and appendicular skeleton across ontogenetic "
            "series."
        ),
        "category": "histology",
        "license": "cc_by_4",
        "doi": "10.9999/sb.2024.0029",
        "version": "v1",
        "species": "Peromyscus",
        "specimen_count": 38,
        "anatomical_region": "Postcranial",
        "lab": "Dsenesky Lab",
        "institution": "Stanford University",
        "file_size_display": "1.4 GB",
        "download_count": 54,
        "tags": [("peromyscus", "default"), ("histology", "blue"), ("tiff", "default"), ("ontogeny", "default")],
        "notebooks": [
            {
                "filename": "histology_segmentation.ipynb",
                "description": "Semi-automated segmentation pipeline for cortical bone boundaries.",
            },
            {
                "filename": "morphometrics_summary.ipynb",
                "description": "Generates summary tables and PCA plots for postcranial measurements.",
            },
        ],
    },
    {
        "title": "ERS_W2 Limb Bone Cross-Section Analysis — Wild Cohort",
        "abstract": (
            "Cross-sectional geometric properties of limb bones from wild ERS_W2 specimens. "
            "Second moment of area, section modulus, and cortical area computed from "
            "periosteal outlines. Raw outlines, processed CSVs, and JSON metadata included."
        ),
        "category": "morphology",
        "license": "cc0",
        "doi": "10.9999/sb.2024.0022",
        "version": "v1",
        "species": "ERS_W2",
        "specimen_count": 71,
        "anatomical_region": "Limb Bones",
        "lab": "Dsenesky Lab",
        "institution": "Stanford University",
        "file_size_display": "8.7 MB",
        "download_count": 118,
        "tags": [("cross-section", "default"), ("biomechanics", "green"), ("csv", "default"), ("json", "default")],
        "notebooks": [],
    },
]


class Command(BaseCommand):
    help = "Seed database with demo datasets from the HTML mockup"

    def handle(self, *args, **options):
        created = 0
        skipped = 0

        for data in DATASETS:
            if Dataset.objects.filter(doi=data["doi"]).exists():
                skipped += 1
                self.stdout.write(f"  skip  {data['title'][:60]}")
                continue

            notebooks_data = data.pop("notebooks")
            tags_data = data.pop("tags")

            ds = Dataset.objects.create(**data)

            for tag_name, color in tags_data:
                tag, _ = Tag.objects.get_or_create(name=tag_name, defaults={"color": color})
                ds.tags.add(tag)

            for nb in notebooks_data:
                Notebook.objects.create(dataset=ds, **nb)

            created += 1
            self.stdout.write(self.style.SUCCESS(f"  created  {ds.title[:60]}"))

        self.stdout.write(f"\nDone — {created} created, {skipped} skipped.")
