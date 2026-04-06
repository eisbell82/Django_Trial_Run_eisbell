import os
import uuid

from django.core.validators import FileExtensionValidator
from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify

ALLOWED_IMAGE_EXTENSIONS = [
    "jpg", "jpeg", "png", "gif", "bmp", "webp",
    "tif", "tiff", "svg", "ico", "heic", "heif",
]
_image_validator = FileExtensionValidator(allowed_extensions=ALLOWED_IMAGE_EXTENSIONS)


def _unique_photo_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower() or ".jpg"
    return f"samples/photos/{uuid.uuid4().hex}{ext}"


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
        ("systems_analysis", "Systems Analysis"),
        ("hydrophobicity", "Hydrophobicity"),
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
    experiment_date = models.DateField(null=True, blank=True)
    lab = models.CharField(max_length=200, blank=True)
    institution = models.CharField(max_length=200, blank=True)
    file_size_display = models.CharField(max_length=50, blank=True, help_text="e.g. 14.2 MB")
    image = models.FileField(upload_to="datasets/images/", null=True, blank=True, validators=[_image_validator])
    download_count = models.PositiveIntegerField(default=0)
    is_private = models.BooleanField(default=False)
    allowed_users = models.ManyToManyField(
        User, blank=True, related_name="accessible_datasets",
        help_text="Users who can view this dataset when it is private."
    )
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
    tab_label = models.CharField(max_length=100, default="Notebook")
    file = models.FileField(upload_to="datasets/notebooks/", null=True, blank=True)
    filename = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    code = models.TextField(blank=True)
    colab_url = models.URLField(blank=True)
    binder_url = models.URLField(blank=True)
    # Dashboard (zip) fields
    zip_file = models.FileField(upload_to="datasets/dashboards/zips/", null=True, blank=True)
    extracted_path = models.CharField(max_length=500, blank=True)
    entry_url = models.CharField(max_length=500, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]

    def __str__(self):
        return self.tab_label



class SampleColumn(models.Model):
    GROUP_CHOICES = [
        ("characteristics", "Sample characteristics"),
        ("data", "Sample data"),
    ]
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="sample_columns")
    name = models.CharField(max_length=200, db_index=True)
    unit = models.CharField(max_length=50, blank=True, default="")
    group = models.CharField(max_length=20, choices=GROUP_CHOICES, default="data")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        unique_together = [("dataset", "name")]

    def __str__(self):
        return self.name


class Sample(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="samples")
    sample_id = models.CharField(max_length=200)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sample_id"]
        unique_together = [("dataset", "sample_id")]

    def __str__(self):
        return self.sample_id

    def value_for(self, column):
        try:
            return self.values.get(column=column).value
        except SampleValue.DoesNotExist:
            return ""


class TodoItem(models.Model):
    text = models.CharField(max_length=500)
    done = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "created_at"]

    def __str__(self):
        return self.text


class AboutPage(models.Model):
    """Singleton model — only one row ever exists (pk=1)."""
    title = models.CharField(max_length=200, default="About")
    content = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    @property
    def content_paragraphs(self):
        """Split content on blank lines into a list of paragraphs."""
        import re
        return [p.strip() for p in re.split(r"\n\s*\n", self.content) if p.strip()]


class DatasetPhoto(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="overview_photos")
    image = models.FileField(upload_to="datasets/overview_photos/", validators=[_image_validator])
    caption = models.CharField(max_length=300, blank=True)
    order = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "uploaded_at"]

    def __str__(self):
        return f"Photo for {self.dataset.title}"


class DocsPage(models.Model):
    """Singleton model — only one row ever exists (pk=1)."""
    title = models.CharField(max_length=200, default="Documentation")
    content = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    @property
    def content_paragraphs(self):
        import re
        return [p.strip() for p in re.split(r"\n\s*\n", self.content) if p.strip()]


class DocsSection(models.Model):
    """An editable section block on the Docs page."""
    TAB_OVERVIEW = 'overview'
    TAB_NAMING   = 'naming'
    TAB_COLUMNS  = 'columns'
    TAB_CHOICES  = [
        (TAB_OVERVIEW, 'Overview'),
        (TAB_NAMING,   'Data Structure'),
        (TAB_COLUMNS,  'Column Structure'),
    ]

    tab     = models.CharField(max_length=20, choices=TAB_CHOICES, default=TAB_OVERVIEW)
    heading = models.CharField(max_length=200)
    body    = models.TextField(blank=True, help_text="Optional paragraph text. Blank lines = new paragraph.")
    rows    = models.TextField(blank=True, help_text="One row per line. Info block: 'Key | Value'. List items: just the text.")
    is_list = models.BooleanField(default=False, help_text="Render rows as ordered list instead of info block.")
    order   = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['tab', 'order', 'pk']

    def __str__(self):
        return f"{self.get_tab_display()} — {self.heading}"

    @property
    def parsed_rows(self):
        result = []
        for line in self.rows.splitlines():
            line = line.strip()
            if not line:
                continue
            if ' | ' in line:
                k, v = line.split(' | ', 1)
                result.append((k.strip(), v.strip()))
            else:
                result.append(('', line))
        return result

    @property
    def body_paragraphs(self):
        import re
        return [p.strip() for p in re.split(r"\n\s*\n", self.body) if p.strip()]


class AboutPhoto(models.Model):
    page = models.ForeignKey(AboutPage, on_delete=models.CASCADE, related_name="photos")
    image = models.FileField(upload_to="about/photos/", validators=[_image_validator])
    caption = models.CharField(max_length=300, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.caption or f"Photo {self.pk}"


class SamplePhoto(models.Model):
    sample = models.ForeignKey(Sample, on_delete=models.CASCADE, related_name="photos")
    image = models.FileField(upload_to=_unique_photo_path, validators=[_image_validator])
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]

    def __str__(self):
        return f"Photo {self.pk} for {self.sample.sample_id}"


class SampleValue(models.Model):
    sample = models.ForeignKey(Sample, on_delete=models.CASCADE, related_name="values")
    column = models.ForeignKey(SampleColumn, on_delete=models.CASCADE, related_name="values")
    value = models.CharField(max_length=1000, blank=True)

    class Meta:
        unique_together = [("sample", "column")]
        indexes = [
            models.Index(fields=["column", "value"], name="samplevalue_col_val_idx"),
        ]
