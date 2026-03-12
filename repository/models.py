from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify


class Tag(models.Model):
    name = models.CharField(max_length=100, unique=True)
    color = models.CharField(
        max_length=20,
        choices=[("default", "Default"), ("green", "Green"), ("blue", "Blue")],
        default="default",
    )

    def __str__(self):
        return self.name


class Dataset(models.Model):
    CATEGORY_CHOICES = [
        ("flame", "Flame"),
        ("mechanical", "Mechanical"),
        ("chemical", "Chemical"),
        ("imaging", "Imaging"),
    ]
    LICENSE_CHOICES = [
        ("cc_by_4", "CC BY 4.0"),
        ("cc_by_nc_4", "CC BY-NC 4.0"),
        ("cc0", "CC0"),
        ("restricted", "Restricted"),
    ]

    title = models.CharField(max_length=300)
    slug = models.SlugField(max_length=320, unique=True, blank=True)
    abstract = models.TextField()
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default="flame")
    license = models.CharField(max_length=20, choices=LICENSE_CHOICES, default="cc_by_4")
    doi = models.CharField(max_length=200, blank=True)
    version = models.CharField(max_length=20, default="v1")
    species = models.CharField(max_length=200, blank=True)
    specimen_count = models.PositiveIntegerField(null=True, blank=True)
    collection_date = models.DateField(null=True, blank=True)
    anatomical_region = models.CharField(max_length=200, blank=True)
    lab = models.CharField(max_length=200, blank=True)
    institution = models.CharField(max_length=200, blank=True)
    file_size_display = models.CharField(max_length=50, blank=True, help_text="e.g. 14.2 MB")
    download_count = models.PositiveIntegerField(default=0)
    tags = models.ManyToManyField(Tag, blank=True, related_name="datasets")
    uploaded_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="datasets"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:320]
        super().save(*args, **kwargs)

    def get_license_display_short(self):
        mapping = {
            "cc_by_4": "CC BY 4.0",
            "cc_by_nc_4": "CC BY-NC 4.0",
            "cc0": "CC0",
            "restricted": "Restricted",
        }
        return mapping.get(self.license, self.license)

    @property
    def notebook_count(self):
        return self.notebooks.count()


class DataFile(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to="datasets/files/")
    filename = models.CharField(max_length=300)
    file_size = models.PositiveIntegerField(default=0, help_text="Size in bytes")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.filename

    @property
    def file_size_display(self):
        size = self.file_size
        if size < 1024:
            return f"{size} B"
        elif size < 1024 ** 2:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 ** 3:
            return f"{size / 1024 ** 2:.1f} MB"
        return f"{size / 1024 ** 3:.1f} GB"


class Notebook(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="notebooks")
    file = models.FileField(upload_to="datasets/notebooks/", null=True, blank=True)
    filename = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    colab_url = models.URLField(blank=True)
    binder_url = models.URLField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.filename
