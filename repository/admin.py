from django.contrib import admin
from .models import (
    Dataset, Tag, DataFile, Notebook,
    Sample, SampleColumn, SampleValue, SamplePhoto,
    AboutPage, AboutPhoto, TodoItem,
)


class DataFileInline(admin.TabularInline):
    model = DataFile
    extra = 1


class NotebookInline(admin.TabularInline):
    model = Notebook
    extra = 1


@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = ["title", "category", "institution", "version", "download_count", "created_at"]
    list_filter = ["category", "license"]
    search_fields = ["title", "abstract", "species", "doi"]
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ["tags"]
    inlines = [DataFileInline, NotebookInline]


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "color"]


@admin.register(DataFile)
class DataFileAdmin(admin.ModelAdmin):
    list_display = ["filename", "dataset", "file_size", "uploaded_at"]


@admin.register(Notebook)
class NotebookAdmin(admin.ModelAdmin):
    list_display = ["filename", "dataset", "uploaded_at"]


class SampleValueInline(admin.TabularInline):
    model = SampleValue
    extra = 0
    fields = ["column", "value"]


class SamplePhotoInline(admin.TabularInline):
    model = SamplePhoto
    extra = 1


@admin.register(Sample)
class SampleAdmin(admin.ModelAdmin):
    list_display = ["sample_id", "dataset"]
    list_filter = ["dataset"]
    search_fields = ["sample_id", "values__value"]
    inlines = [SampleValueInline, SamplePhotoInline]


@admin.register(SampleColumn)
class SampleColumnAdmin(admin.ModelAdmin):
    list_display = ["name", "unit", "dataset", "order"]
    list_filter = ["dataset"]


@admin.register(SampleValue)
class SampleValueAdmin(admin.ModelAdmin):
    list_display = ["sample", "column", "value"]
    list_filter = ["column"]
    search_fields = ["value"]


class AboutPhotoInline(admin.TabularInline):
    model = AboutPhoto
    extra = 1


@admin.register(AboutPage)
class AboutPageAdmin(admin.ModelAdmin):
    inlines = [AboutPhotoInline]


@admin.register(TodoItem)
class TodoItemAdmin(admin.ModelAdmin):
    list_display = ["text", "done", "order", "created_at"]
    list_filter = ["done"]
