from django.contrib import admin
from .models import Dataset, Tag, DataFile, Notebook


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
