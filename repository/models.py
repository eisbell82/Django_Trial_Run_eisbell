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
    experiment_date = models.DateField(null=True, blank=True)
    lab = models.CharField(max_length=200, blank=True)
    institution = models.CharField(max_length=200, blank=True)
    file_size_display = models.CharField(max_length=50, blank=True, help_text="e.g. 14.2 MB")
    image = models.ImageField(upload_to="datasets/images/", null=True, blank=True)
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
    name = models.CharField(max_length=200)
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


class AboutPhoto(models.Model):
    page = models.ForeignKey(AboutPage, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="about/photos/")
    caption = models.CharField(max_length=300, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.caption or f"Photo {self.pk}"


class SamplePhoto(models.Model):
    sample = models.ForeignKey(Sample, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="samples/photos/")
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
