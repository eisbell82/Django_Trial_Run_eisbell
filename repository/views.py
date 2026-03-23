import csv
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseRedirect, HttpResponse, JsonResponse
from django.urls import reverse
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.db.models import Q, Count
from django.utils.http import url_has_allowed_host_and_scheme
from django.conf import settings

from .models import Dataset, Tag, DataFile, Notebook, Sample, SampleColumn, SampleValue, SamplePhoto, TodoItem, AboutPage, AboutPhoto, DocsPage, DatasetPhoto, DocsSection
from .forms import DatasetUploadForm, DataFileForm, NotebookForm

ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".xlsx", ".json", ".tiff", ".tif", ".zip", ".tsv", ".txt"}

ADMIN_UPLOAD_LIMIT = 500 * 1024 * 1024   # 500 MB
USER_UPLOAD_LIMIT  = 150 * 1024 * 1024   # 150 MB

# Formats browsers cannot render in <img> tags — convert to JPEG on upload
_NON_WEB_IMAGE_EXTS = {".tif", ".tiff", ".heic", ".heif"}


def _to_web_image(uploaded_file):
    """
    If uploaded_file has a non-web-renderable extension, convert it to JPEG
    using Pillow and return a Django ContentFile with a .jpg name.
    Otherwise return the original file unchanged.
    """
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in _NON_WEB_IMAGE_EXTS:
        return uploaded_file
    from PIL import Image
    from django.core.files.base import ContentFile
    import io
    img = Image.open(uploaded_file)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail((2000, 2000), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    base = os.path.splitext(uploaded_file.name)[0]
    return ContentFile(buf.getvalue(), name=f"{base}.jpg")


def _upload_limit(user):
    return ADMIN_UPLOAD_LIMIT if (user and user.is_staff) else USER_UPLOAD_LIMIT


def _redirect_to_tab(slug, tab):
    """Redirect to a dataset detail page and land on a specific tab."""
    url = reverse("repository:detail", kwargs={"slug": slug}) + f"#{tab}"
    return HttpResponseRedirect(url)


def home(request):
    category  = request.GET.get("category", "")
    query     = request.GET.get("q", "")
    sort      = request.GET.get("sort", "date")
    order     = request.GET.get("order", "desc")
    f_lab     = request.GET.get("lab", "")
    f_inst    = request.GET.get("institution", "")
    f_license = request.GET.get("license", "")

    datasets = _visible_datasets(request.user).prefetch_related("tags", "notebooks")

    if category and category != "all":
        datasets = datasets.filter(category=category)
    if query:
        datasets = datasets.filter(
            Q(title__icontains=query)
            | Q(abstract__icontains=query)
            | Q(tags__name__icontains=query)
        ).distinct()
    if f_lab:
        datasets = datasets.filter(lab=f_lab)
    if f_inst:
        datasets = datasets.filter(institution=f_inst)
    if f_license:
        datasets = datasets.filter(license=f_license)

    sort_field = {"date": "created_at", "downloads": "download_count", "title": "title"}.get(sort, "created_at")
    if order == "asc":
        datasets = datasets.order_by(sort_field)
    else:
        datasets = datasets.order_by(f"-{sort_field}")

    stats = Dataset.objects.aggregate(
        total_count=Count("id"),
        notebook_count=Count("notebooks"),
        contributor_count=Count("uploaded_by", distinct=True),
    )

    # Distinct values for filter dropdowns (non-blank only)
    lab_list         = Dataset.objects.exclude(lab="").values_list("lab", flat=True).distinct().order_by("lab")
    institution_list = Dataset.objects.exclude(institution="").values_list("institution", flat=True).distinct().order_by("institution")

    context = {
        "datasets": datasets,
        "total_count": stats["total_count"],
        "notebook_count": stats["notebook_count"],
        "contributor_count": stats["contributor_count"],
        "active_category": category or "all",
        "query": query,
        "sort": sort,
        "order": order,
        "f_lab": f_lab,
        "f_inst": f_inst,
        "f_license": f_license,
        "lab_list": lab_list,
        "institution_list": institution_list,
        "category_choices": Dataset.CATEGORY_CHOICES,
        "license_choices": Dataset.LICENSE_CHOICES,
        "sort_options": [("date", "Date"), ("downloads", "Downloads"), ("title", "Title")],
    }
    return render(request, "repository/home.html", context)


def dataset_detail(request, slug):
    dataset = get_object_or_404(
        Dataset.objects.prefetch_related("tags", "notebooks", "files"), slug=slug
    )

    if not _can_view(request.user, dataset):
        messages.error(request, "This dataset is private.")
        return redirect("repository:home")

    if request.method == "POST" and "download" in request.POST:
        dataset.download_count += 1
        dataset.save(update_fields=["download_count"])
        return redirect("repository:detail", slug=slug)

    sort_col  = request.GET.get("sort_col", "")
    sort_dir  = request.GET.get("sort_dir", "asc")
    try:
        per_page = int(request.GET.get("per_page", 25))
        if per_page not in (25, 50, 100):
            per_page = 25
    except ValueError:
        per_page = 25
    try:
        page_num = int(request.GET.get("page", 1))
    except ValueError:
        page_num = 1

    columns = list(dataset.sample_columns.all())
    col_name_map = {col.name: col for col in columns}
    reverse_sort = sort_dir == "desc"

    from django.core.paginator import Paginator

    if not sort_col:
        # No sort — DB-level pagination (Django issues efficient LIMIT/OFFSET)
        qs = dataset.samples.all()
        paginator = Paginator(qs, per_page)
        page_obj = paginator.get_page(page_num)
        page_samples = list(
            dataset.samples.filter(pk__in=[s.pk for s in page_obj.object_list])
            .prefetch_related("values", "photos")
        )
        # Restore DB order
        pk_pos = {s.pk: i for i, s in enumerate(page_obj.object_list)}
        page_samples.sort(key=lambda s: pk_pos.get(s.pk, 0))
    else:
        # Sort in Python (numeric-aware), paginate PKs, fetch full data for page only
        if sort_col == "sample_id":
            pairs = list(dataset.samples.values_list("pk", "sample_id"))
            pairs.sort(key=lambda t: _sort_key(t[1]), reverse=reverse_sort)
        else:
            col_obj = col_name_map.get(sort_col)
            if col_obj:
                val_lookup = dict(
                    SampleValue.objects.filter(sample__dataset=dataset, column=col_obj)
                    .values_list("sample_id", "value")
                )
                all_pks = list(dataset.samples.values_list("pk", flat=True))
                pairs = [(pk, val_lookup.get(pk, "")) for pk in all_pks]
                pairs.sort(key=lambda t: _sort_key(t[1]), reverse=reverse_sort)
            else:
                pairs = [(pk, "") for pk in dataset.samples.values_list("pk", flat=True)]

        paginator = Paginator(pairs, per_page)
        page_obj = paginator.get_page(page_num)
        page_pks = [pk for pk, _ in page_obj.object_list]
        pk_to_sample = {
            s.pk: s
            for s in dataset.samples.filter(pk__in=page_pks).prefetch_related("values", "photos")
        }
        page_samples = [pk_to_sample[pk] for pk in page_pks if pk in pk_to_sample]

    # Build row data for current page only
    for s in page_samples:
        val_map = {v.column_id: v.value for v in s.values.all()}
        s.row_with_cols = [(col, val_map.get(col.pk, "")) for col in columns]
        s.photos_list = list(s.photos.all())

    samples = page_samples

    # Column names across all experiments, sorted by how many experiments use them
    existing_col_names = [
        row["name"]
        for row in (
            SampleColumn.objects.values("name")
            .annotate(cnt=Count("dataset", distinct=True))
            .order_by("-cnt", "name")
        )
    ]

    # Units previously used for columns sharing the same name (for per-column unit suggestions)
    col_names = [col.name for col in columns]
    unit_rows = (
        SampleColumn.objects.filter(name__in=col_names)
        .exclude(unit="")
        .values("name", "unit")
        .distinct()
    )
    unit_sugs_by_name = {}
    for row in unit_rows:
        lst = unit_sugs_by_name.setdefault(row["name"], [])
        if row["unit"] not in lst:
            lst.append(row["unit"])
    for col in columns:
        col.unit_suggestions = unit_sugs_by_name.get(col.name, [])

    char_columns = [c for c in columns if c.group == "characteristics"]
    data_columns  = [c for c in columns if c.group == "data"]

    notebooks = list(dataset.notebooks.all())
    context = {
        "dataset": dataset,
        "notebooks": notebooks,
        "sample_columns": columns,
        "char_columns": char_columns,
        "data_columns": data_columns,
        "samples": samples,
        "page_obj": page_obj,
        "total_samples": paginator.count,
        "per_page": per_page,
        "sort_col": sort_col,
        "sort_dir": sort_dir,
        "page_sizes": [25, 50, 100],
        "suggested_column_names": existing_col_names,
        "current_col_names": [col.name for col in columns],
        "overview_photos": dataset.overview_photos.all(),
    }
    return render(request, "repository/detail.html", context)


@login_required
def upload_dataset(request):
    if request.method == "POST":
        form = DatasetUploadForm(request.POST)
        data_file_form = DataFileForm(request.POST, request.FILES)
        notebook_form = NotebookForm(request.POST, request.FILES)

        if form.is_valid():
            dataset = form.save(commit=False)
            dataset.uploaded_by = request.user
            dataset.save()

            # Handle tags
            tags_text = form.cleaned_data.get("tags_text", "")
            if tags_text:
                for tag_name in [t.strip() for t in tags_text.split(",") if t.strip()]:
                    tag, _ = Tag.objects.get_or_create(name=tag_name.lower())
                    dataset.tags.add(tag)

            # Handle data file upload
            if request.FILES.get("data_file"):
                uploaded = request.FILES["data_file"]
                import os
                ext = os.path.splitext(uploaded.name)[1].lower()
                if ext not in ALLOWED_UPLOAD_EXTENSIONS:
                    messages.error(request, f"File type '{ext}' is not allowed.")
                    dataset.delete()
                    return render(request, "repository/upload.html", {
                        "form": form,
                        "data_file_form": data_file_form,
                        "notebook_form": notebook_form,
                    })
                if uploaded.size > _upload_limit(request.user):
                    limit_mb = _upload_limit(request.user) // (1024 * 1024)
                    messages.error(request, f"File exceeds the {limit_mb} MB maximum size limit.")
                    dataset.delete()
                    return render(request, "repository/upload.html", {
                        "form": form,
                        "data_file_form": data_file_form,
                        "notebook_form": notebook_form,
                    })
                DataFile.objects.create(
                    dataset=dataset,
                    file=uploaded,
                    filename=uploaded.name,
                    file_size=uploaded.size,
                )
                dataset.file_size_display = _format_bytes(uploaded.size)
                dataset.save(update_fields=["file_size_display"])

            # Handle notebook upload
            if request.FILES.get("notebook_file"):
                uploaded = request.FILES["notebook_file"]
                Notebook.objects.create(
                    dataset=dataset,
                    file=uploaded,
                    filename=uploaded.name,
                )

            messages.success(request, "Dataset published successfully.")
            return redirect("repository:detail", slug=dataset.slug)
    else:
        form = DatasetUploadForm()
        data_file_form = DataFileForm()
        notebook_form = NotebookForm()

    return render(request, "repository/upload.html", {
        "form": form,
        "data_file_form": data_file_form,
        "notebook_form": notebook_form,
    })


def login_view(request):
    if request.user.is_authenticated:
        return redirect("repository:home")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.GET.get("next", "")
            if next_url and url_has_allowed_host_and_scheme(
                url=next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)
            return redirect("repository:home")
        messages.error(request, "Invalid credentials. Please try again.")

    return render(request, "repository/login.html")


def logout_view(request):
    if request.method == "POST":
        logout(request)
    return redirect("repository:home")


def register_view(request):
    if request.user.is_authenticated:
        return redirect("repository:home")

    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_staff = False
            user.is_superuser = False
            user.save()
            login(request, user)
            messages.success(request, f"Welcome, {user.username}! Your account has been created.")
            return redirect("repository:home")
    else:
        form = UserCreationForm()

    return render(request, "repository/register.html", {"form": form})


def collections_view(request):
    query     = request.GET.get("q", "")
    category  = request.GET.get("category", "")
    sort      = request.GET.get("sort", "date")
    order     = request.GET.get("order", "desc")
    f_lab     = request.GET.get("lab", "")
    f_inst    = request.GET.get("institution", "")
    f_license = request.GET.get("license", "")

    sort_field = {"date": "created_at", "downloads": "download_count", "title": "title"}.get(sort, "created_at")
    order_prefix = "" if order == "asc" else "-"

    base_qs = _visible_datasets(request.user).prefetch_related("tags")
    if query:
        base_qs = base_qs.filter(
            Q(title__icontains=query)
            | Q(abstract__icontains=query)
            | Q(tags__name__icontains=query)
        ).distinct()
    if f_lab:
        base_qs = base_qs.filter(lab=f_lab)
    if f_inst:
        base_qs = base_qs.filter(institution=f_inst)
    if f_license:
        base_qs = base_qs.filter(license=f_license)
    base_qs = base_qs.order_by(f"{order_prefix}{sort_field}")

    categories_to_show = [category] if (category and category != "all") else [k for k, _ in Dataset.CATEGORY_CHOICES]
    collections = []
    total_results = 0
    for key in categories_to_show:
        label = dict(Dataset.CATEGORY_CHOICES).get(key, key)
        qs = base_qs.filter(category=key)
        count = qs.count()
        if count:
            collections.append({"key": key, "label": label, "datasets": qs, "total": count})
            total_results += count

    lab_list         = Dataset.objects.exclude(lab="").values_list("lab", flat=True).distinct().order_by("lab")
    institution_list = Dataset.objects.exclude(institution="").values_list("institution", flat=True).distinct().order_by("institution")

    return render(request, "repository/collections.html", {
        "collections": collections,
        "total_results": total_results,
        "query": query,
        "sort": sort,
        "order": order,
        "active_category": category or "all",
        "f_lab": f_lab,
        "f_inst": f_inst,
        "f_license": f_license,
        "lab_list": lab_list,
        "institution_list": institution_list,
        "category_choices": Dataset.CATEGORY_CHOICES,
        "license_choices": Dataset.LICENSE_CHOICES,
        "sort_options": [("date", "Date"), ("downloads", "Downloads"), ("title", "Title")],
    })


@login_required
def clear_samples(request, slug):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return redirect("repository:detail", slug=slug)
    if request.method == "POST":
        count = dataset.samples.count()
        dataset.samples.all().delete()  # cascades to SampleValue and SamplePhoto
        messages.success(request, f"Cleared {count} sample{'s' if count != 1 else ''} from this experiment.")
    return redirect("repository:detail", slug=slug)


@login_required
def delete_dataset(request, slug):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not (request.user == dataset.uploaded_by or request.user.is_staff):
        messages.error(request, "You do not have permission to delete this dataset.")
        return redirect("repository:detail", slug=slug)
    if request.method == "POST":
        dataset.delete()
        messages.success(request, "Dataset deleted.")
        return redirect("repository:home")
    return render(request, "repository/delete_confirm.html", {"dataset": dataset})


def _can_edit(user, dataset):
    return user.is_authenticated and (user == dataset.uploaded_by or user.is_staff)


def _can_view(user, dataset):
    if not dataset.is_private:
        return True
    if not user.is_authenticated:
        return False
    return user.is_staff or user == dataset.uploaded_by or dataset.allowed_users.filter(pk=user.pk).exists()


def _visible_datasets(user):
    """Return a queryset of datasets visible to the given user."""
    if user.is_authenticated and user.is_staff:
        return Dataset.objects.all()
    if user.is_authenticated:
        from django.db.models import Q
        return Dataset.objects.filter(
            Q(is_private=False) |
            Q(uploaded_by=user) |
            Q(allowed_users=user)
        ).distinct()
    return Dataset.objects.filter(is_private=False)


@login_required
def add_file(request, slug):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return _redirect_to_tab(slug, "tab-files")
    if request.method == "POST" and request.FILES.get("data_file"):
        import os
        uploaded = request.FILES["data_file"]
        ext = os.path.splitext(uploaded.name)[1].lower()
        if ext not in ALLOWED_UPLOAD_EXTENSIONS:
            messages.error(request, f"File type '{ext}' is not allowed.")
        elif uploaded.size > _upload_limit(request.user):
            limit_mb = _upload_limit(request.user) // (1024 * 1024)
            messages.error(request, f"File exceeds the {limit_mb} MB maximum size limit.")
        else:
            DataFile.objects.create(
                dataset=dataset,
                file=uploaded,
                filename=uploaded.name,
                file_size=uploaded.size,
            )
            messages.success(request, f"'{uploaded.name}' added.")
    return _redirect_to_tab(slug, "tab-files")


@login_required
def delete_file(request, slug, pk):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return _redirect_to_tab(slug, "tab-files")
    if request.method == "POST":
        DataFile.objects.filter(pk=pk, dataset=dataset).delete()
    return _redirect_to_tab(slug, "tab-files")

def _find_entry_html(extract_dir):
    candidates = []
    for root, dirs, files in os.walk(extract_dir):
        for fname in files:
            if fname.lower() == "index.html":
                candidates.append(os.path.join(root, fname))
    if not candidates:
        return None
    docs_candidates = [p for p in candidates if os.sep + "docs" + os.sep in p]
    return docs_candidates[0] if docs_candidates else candidates[0]


def _unwrap_single_dir(extract_dir):
    """If the zip contained one top-level folder, return that folder path; else extract_dir."""
    try:
        entries = [e for e in os.listdir(extract_dir) if not e.startswith("__MACOSX")]
        if len(entries) == 1:
            candidate = os.path.join(extract_dir, entries[0])
            if os.path.isdir(candidate):
                return candidate
    except OSError:
        pass
    return extract_dir


@login_required
def rebuild_dashboard(request, slug, pk):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return redirect("repository:detail", slug=slug)
    nb = get_object_or_404(Notebook, pk=pk, dataset=dataset)

    if request.method == "POST":
        data_zip = request.FILES.get("data_zip")
        if not data_zip:
            messages.error(request, "Please select a data zip file.")
            return render(request, "repository/rebuild_dashboard.html",
                          {"dataset": dataset, "notebook": nb})
        if not data_zip.name.lower().endswith(".zip"):
            messages.error(request, "File must be a .zip archive.")
            return render(request, "repository/rebuild_dashboard.html",
                          {"dataset": dataset, "notebook": nb})

        # Write upload to a temp file so we can open it as a ZipFile
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            for chunk in data_zip.chunks():
                tmp.write(chunk)
            tmp_zip_path = tmp.name

        try:
            # Extract data zip → input staging area
            input_extract = os.path.join(
                settings.MEDIA_ROOT, "dashboard_input", str(nb.pk)
            )
            if os.path.isdir(input_extract):
                shutil.rmtree(input_extract)
            os.makedirs(input_extract, exist_ok=True)

            try:
                with zipfile.ZipFile(tmp_zip_path, "r") as zf:
                    zf.extractall(input_extract)
            except zipfile.BadZipFile:
                messages.error(request, "The file is not a valid zip archive.")
                return render(request, "repository/rebuild_dashboard.html",
                              {"dataset": dataset, "notebook": nb})

            input_dir = _unwrap_single_dir(input_extract)

            # Output directory (same place as existing dashboard extract)
            output_dir = os.path.join(
                settings.MEDIA_ROOT, "datasets", "dashboards", str(nb.pk)
            )
            if os.path.isdir(output_dir):
                shutil.rmtree(output_dir)
            os.makedirs(output_dir, exist_ok=True)

            # assets/ dir is where build_dashboard.py lives
            assets_dir = os.path.join(settings.BASE_DIR, "assets")
            script = os.path.join(assets_dir, "build_dashboard.py")

            result = subprocess.run(
                [sys.executable, script,
                 "--repo", assets_dir,
                 "--data", input_dir,
                 "--out",  output_dir],
                capture_output=True, text=True, timeout=300,
            )

            if result.returncode != 0:
                err_snippet = (result.stderr or result.stdout or "")[-3000:]
                messages.error(request, f"Build failed:\n{err_snippet}")
                return render(request, "repository/rebuild_dashboard.html",
                              {"dataset": dataset, "notebook": nb})

            entry = _find_entry_html(output_dir)
            if entry:
                rel = os.path.relpath(entry, settings.MEDIA_ROOT).replace(os.sep, "/")
                nb.entry_url = settings.MEDIA_URL + rel
            nb.extracted_path = os.path.relpath(output_dir, settings.MEDIA_ROOT)
            nb.save(update_fields=["entry_url", "extracted_path"])

            messages.success(request, "Dashboard rebuilt from uploaded data.")
            return _redirect_to_tab(slug, f"tab-nb-{nb.pk}")
        finally:
            os.unlink(tmp_zip_path)

    return render(request, "repository/rebuild_dashboard.html",
                  {"dataset": dataset, "notebook": nb})


@login_required
def add_notebook(request, slug):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return redirect("repository:detail", slug=slug)
    if dataset.notebooks.count() >= 3:
        messages.error(request, "Maximum of 3 tabs per experiment.")
        return redirect("repository:detail", slug=slug)
    if request.method == "POST":
        tab_label = request.POST.get("tab_label", "").strip() or "Notebook"
        description = request.POST.get("description", "").strip()
        code = request.POST.get("code", "").strip()
        colab_url = request.POST.get("colab_url", "").strip()
        binder_url = request.POST.get("binder_url", "").strip()
        nb = Notebook(dataset=dataset, tab_label=tab_label, description=description,
                      code=code, colab_url=colab_url, binder_url=binder_url)
        if request.FILES.get("notebook_file"):
            uploaded = request.FILES["notebook_file"]
            nb.file = uploaded
            nb.filename = uploaded.name
        zip_file = request.FILES.get("dashboard_zip")
        if zip_file:
            if not zip_file.name.lower().endswith(".zip"):
                messages.error(request, "Dashboard upload must be a .zip file.")
                return render(request, "repository/add_notebook.html", {"dataset": dataset})
            nb.zip_file = zip_file
            nb.save()
            extract_dir = os.path.join(settings.MEDIA_ROOT, "datasets", "dashboards", str(nb.pk))
            os.makedirs(extract_dir, exist_ok=True)
            try:
                with zipfile.ZipFile(nb.zip_file.path, "r") as zf:
                    zf.extractall(extract_dir)
            except zipfile.BadZipFile:
                nb.delete()
                shutil.rmtree(extract_dir, ignore_errors=True)
                messages.error(request, "The file is not a valid zip archive.")
                return render(request, "repository/add_notebook.html", {"dataset": dataset})
            entry = _find_entry_html(extract_dir)
            if entry:
                rel = os.path.relpath(entry, settings.MEDIA_ROOT).replace(os.sep, "/")
                nb.entry_url = settings.MEDIA_URL + rel
            nb.extracted_path = os.path.relpath(extract_dir, settings.MEDIA_ROOT)
            nb.save(update_fields=["entry_url", "extracted_path"])
        else:
            nb.save()
        messages.success(request, f"Tab '{tab_label}' added.")
        return redirect("repository:detail", slug=slug)
    return render(request, "repository/add_notebook.html", {"dataset": dataset})


@login_required
def delete_notebook(request, slug, pk):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return redirect("repository:detail", slug=slug)
    if request.method == "POST":
        nb = get_object_or_404(Notebook, pk=pk, dataset=dataset)
        extract_dir = os.path.join(settings.MEDIA_ROOT, nb.extracted_path) if nb.extracted_path else None
        nb.delete()
        if extract_dir and os.path.isdir(extract_dir):
            shutil.rmtree(extract_dir, ignore_errors=True)
    return redirect("repository:detail", slug=slug)


@login_required
def add_sample_column(request, slug):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return _redirect_to_tab(slug, "tab-samples")
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        group = request.POST.get("group", "data")
        if group not in ("characteristics", "data"):
            group = "data"
        if name:
            order = dataset.sample_columns.count()
            SampleColumn.objects.get_or_create(dataset=dataset, name=name, defaults={"order": order, "group": group})
    return _redirect_to_tab(slug, "tab-samples")


@login_required
def delete_sample_column(request, slug, col_id):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return _redirect_to_tab(slug, "tab-samples")
    if request.method == "POST":
        SampleColumn.objects.filter(id=col_id, dataset=dataset).delete()
    return _redirect_to_tab(slug, "tab-samples")


@login_required
def add_sample(request, slug):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return _redirect_to_tab(slug, "tab-samples")
    _seen = set()
    columns = [c for c in dataset.sample_columns.all() if not (_seen.__contains__(c.name.strip().lower()) or _seen.add(c.name.strip().lower()))]
    if request.method == "POST":
        sample_id = request.POST.get("sample_id", "").strip()
        if sample_id:
            sample, _ = Sample.objects.get_or_create(dataset=dataset, sample_id=sample_id)
            sample.notes = request.POST.get("notes", "").strip()[:250]
            sample.save()
            for col in columns:
                val = request.POST.get(f"col_{col.id}", "").strip()
                SampleValue.objects.update_or_create(
                    sample=sample, column=col, defaults={"value": val}
                )
            messages.success(request, f"Sample '{sample_id}' saved.")
        return _redirect_to_tab(slug, "tab-samples")
    return render(request, "repository/add_sample.html", {"dataset": dataset, "columns": columns})


@login_required
def delete_sample(request, slug, pk):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return _redirect_to_tab(slug, "tab-samples")
    if request.method == "POST":
        Sample.objects.filter(pk=pk, dataset=dataset).delete()
    return _redirect_to_tab(slug, "tab-samples")


@login_required
def edit_sample(request, slug, pk):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return _redirect_to_tab(slug, "tab-samples")
    sample = get_object_or_404(Sample, pk=pk, dataset=dataset)
    _seen = set()
    columns = [c for c in dataset.sample_columns.all() if not (_seen.__contains__(c.name.strip().lower()) or _seen.add(c.name.strip().lower()))]

    # Build ordered sample list for prev/next navigation
    all_pks = list(dataset.samples.order_by("sample_id").values_list("pk", flat=True))
    try:
        idx = all_pks.index(sample.pk)
    except ValueError:
        idx = 0
    prev_pk = all_pks[idx - 1] if idx > 0 else None
    next_pk = all_pks[idx + 1] if idx < len(all_pks) - 1 else None

    if request.method == "POST":
        sample_id = request.POST.get("sample_id", "").strip()
        if sample_id:
            sample.sample_id = sample_id
            sample.notes = request.POST.get("notes", "").strip()[:250]
            sample.save()
            for col in columns:
                val = request.POST.get(f"col_{col.id}", "").strip()
                SampleValue.objects.update_or_create(
                    sample=sample, column=col, defaults={"value": val}
                )
        # Silent autosave (fetch / sendBeacon) — just return 200, no redirect
        if request.POST.get("autosave") == "1":
            return HttpResponse("ok")
        messages.success(request, f"Sample '{sample.sample_id}' updated.")
        return _redirect_to_tab(slug, "tab-samples")

    current_values = {v.column_id: v.value for v in sample.values.all()}
    column_values = [(col, current_values.get(col.id, "")) for col in columns]
    return render(request, "repository/edit_sample.html", {
        "dataset": dataset,
        "sample": sample,
        "column_values": column_values,
        "prev_pk": prev_pk,
        "next_pk": next_pk,
        "current_idx": idx + 1,
        "total_samples": len(all_pks),
    })


@login_required
def save_sample_notes(request, slug, pk):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        return HttpResponse(status=403)
    if request.method == "POST":
        sample = get_object_or_404(Sample, pk=pk, dataset=dataset)
        sample.notes = request.POST.get("notes", "").strip()[:250]
        sample.save()
        return HttpResponse(status=204)
    return HttpResponse(status=405)


@login_required
def upload_sample_photo(request, slug, pk):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return _redirect_to_tab(slug, "tab-samples")
    sample = get_object_or_404(Sample, pk=pk, dataset=dataset)
    if request.method == "POST":
        photo = request.FILES.get("photo")
        if photo:
            SamplePhoto.objects.create(sample=sample, image=_to_web_image(photo))
    return _redirect_to_tab(slug, "tab-samples")


@login_required
def delete_sample_photo(request, slug, sample_pk, photo_pk):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return _redirect_to_tab(slug, "tab-samples")
    photo = get_object_or_404(SamplePhoto, pk=photo_pk, sample__pk=sample_pk, sample__dataset=dataset)
    if request.method == "POST":
        photo.image.delete(save=False)
        photo.delete()
    return _redirect_to_tab(slug, "tab-samples")


@login_required
def rename_sample_column(request, slug, col_id):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return _redirect_to_tab(slug, "tab-samples")
    if request.method == "POST":
        new_name = request.POST.get("name", "").strip()
        if new_name:
            SampleColumn.objects.filter(id=col_id, dataset=dataset).update(name=new_name)
    if request.headers.get("X-Fetch"):
        return HttpResponse(status=204)
    return _redirect_to_tab(slug, "tab-samples")


@login_required
def set_column_unit(request, slug, col_id):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return _redirect_to_tab(slug, "tab-samples")
    if request.method == "POST":
        unit = request.POST.get("unit", "").strip()
        SampleColumn.objects.filter(id=col_id, dataset=dataset).update(unit=unit)
    if request.headers.get("X-Fetch"):
        return HttpResponse(status=204)
    return _redirect_to_tab(slug, "tab-samples")


@login_required
def set_column_group(request, slug, col_id):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return _redirect_to_tab(slug, "tab-samples")
    if request.method == "POST":
        group = request.POST.get("group", "data")
        if group in ("characteristics", "data"):
            SampleColumn.objects.filter(id=col_id, dataset=dataset).update(group=group)
    return _redirect_to_tab(slug, "tab-samples")


@login_required
def move_sample_column(request, slug, col_id):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        return _redirect_to_tab(slug, "tab-samples")
    if request.method == "POST":
        direction = request.POST.get("direction")
        columns = list(dataset.sample_columns.order_by("order", "id"))
        # Normalize orders
        for i, col in enumerate(columns):
            if col.order != i:
                col.order = i
        SampleColumn.objects.bulk_update(columns, ["order"])
        idx = next((i for i, c in enumerate(columns) if c.id == int(col_id)), None)
        if idx is not None:
            if direction == "left" and idx > 0:
                columns[idx].order, columns[idx - 1].order = idx - 1, idx
                SampleColumn.objects.bulk_update([columns[idx], columns[idx - 1]], ["order"])
            elif direction == "right" and idx < len(columns) - 1:
                columns[idx].order, columns[idx + 1].order = idx + 1, idx
                SampleColumn.objects.bulk_update([columns[idx], columns[idx + 1]], ["order"])
        if request.headers.get("X-Fetch"):
            return HttpResponse(status=204)
    return _redirect_to_tab(slug, "tab-samples")


@login_required
def upload_csv_samples(request, slug):
    import csv, io
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return _redirect_to_tab(slug, "tab-samples")
    if request.method == "POST" and request.FILES.get("csv_file"):
        try:
            text = request.FILES["csv_file"].read().decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            headers = list(reader.fieldnames or [])
            sid_col = headers[0] if headers else None
            notes_col = next((h for h in headers if h.strip().lower() == "sample notes"), None)
            data_headers = [h for h in headers if h != sid_col and h != notes_col]

            # Read all rows up-front so we can detect dominant data type per column
            rows = [r for r in reader if sid_col and r.get(sid_col, "").strip()]

            def _is_numeric(val):
                try:
                    float(str(val).strip().replace(",", ""))
                    return True
                except (ValueError, AttributeError):
                    return False

            def _detect_group(header):
                vals = [r.get(header, "").strip() for r in rows if r.get(header, "").strip()]
                if not vals:
                    return "data"
                return "data" if sum(_is_numeric(v) for v in vals) / len(vals) > 0.5 else "characteristics"

            # get_or_create columns — group is auto-detected from dominant data type
            col_map = {}
            for h in data_headers:
                col_name = h.strip()
                col_group = _detect_group(h)
                col, _ = SampleColumn.objects.get_or_create(
                    dataset=dataset, name=col_name,
                    defaults={"order": dataset.sample_columns.count(), "group": col_group},
                )
                col_map[h] = col
            all_sids = [r[sid_col].strip() for r in rows]

            # Fetch existing samples in one query, bulk-create new ones
            existing_samples = {
                s.sample_id: s
                for s in Sample.objects.filter(dataset=dataset, sample_id__in=all_sids)
            }
            # Build notes lookup from rows for bulk_create
            notes_by_sid = {}
            if notes_col:
                for r in rows:
                    sid = r[sid_col].strip()
                    notes_by_sid[sid] = r.get(notes_col, "").strip()

            new_sids = [sid for sid in dict.fromkeys(all_sids) if sid not in existing_samples]
            if new_sids:
                Sample.objects.bulk_create(
                    [Sample(dataset=dataset, sample_id=sid, notes=notes_by_sid.get(sid, "")) for sid in new_sids],
                    ignore_conflicts=True,
                )
                existing_samples = {
                    s.sample_id: s
                    for s in Sample.objects.filter(dataset=dataset, sample_id__in=all_sids)
                }

            # Fetch existing values in one query
            sample_pks = [s.pk for s in existing_samples.values()]
            col_pks = [c.pk for c in col_map.values()]
            existing_values = {
                (sv.sample_id, sv.column_id): sv
                for sv in SampleValue.objects.filter(
                    sample_id__in=sample_pks, column_id__in=col_pks
                )
            }

            notes_to_update = []
            to_create, to_update = [], []
            for row in rows:
                sid = row[sid_col].strip()
                sample = existing_samples.get(sid)
                if not sample:
                    continue
                if notes_col:
                    new_notes = row.get(notes_col, "").strip()
                    if sample.notes != new_notes:
                        sample.notes = new_notes
                        notes_to_update.append(sample)
                for h, col in col_map.items():
                    val = row.get(h, "").strip()
                    key = (sample.pk, col.pk)
                    if key in existing_values:
                        sv = existing_values[key]
                        if sv.value != val:
                            sv.value = val
                            to_update.append(sv)
                    else:
                        to_create.append(SampleValue(sample=sample, column=col, value=val))
            if notes_to_update:
                Sample.objects.bulk_update(notes_to_update, ["notes"])

            if to_create:
                SampleValue.objects.bulk_create(to_create, ignore_conflicts=True)
            if to_update:
                SampleValue.objects.bulk_update(to_update, ["value"])

            count = len(set(all_sids))
            messages.success(request, f"Imported {count} sample(s) from CSV.")
        except Exception as e:
            messages.error(request, f"Error reading CSV: {e}")
    return _redirect_to_tab(slug, "tab-samples")


@login_required
def edit_dataset(request, slug):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return redirect("repository:detail", slug=slug)
    if request.method == "POST":
        form = DatasetUploadForm(request.POST, instance=dataset)
        if form.is_valid():
            ds = form.save(commit=False)
            ds.is_private = "is_private" in request.POST
            ds.save()
            ds.tags.clear()
            tags_text = form.cleaned_data.get("tags_text", "")
            if tags_text:
                for tag_name in [t.strip() for t in tags_text.split(",") if t.strip()]:
                    tag, _ = Tag.objects.get_or_create(name=tag_name.lower())
                    ds.tags.add(tag)
            messages.success(request, "Dataset updated.")
            return redirect("repository:detail", slug=ds.slug)
    else:
        existing_tags = ", ".join(dataset.tags.values_list("name", flat=True))
        form = DatasetUploadForm(instance=dataset, initial={"tags_text": existing_tags})
    allowed = dataset.allowed_users.all()
    from django.contrib.auth.models import User as AuthUser
    excluded_ids = set(allowed.values_list("pk", flat=True))
    if dataset.uploaded_by_id:
        excluded_ids.add(dataset.uploaded_by_id)
    candidate_users = list(
        AuthUser.objects.exclude(pk__in=excluded_ids)
        .values_list("username", flat=True)
        .order_by("username")
    )
    return render(request, "repository/edit_dataset.html", {
        "form": form,
        "dataset": dataset,
        "allowed_users": allowed,
        "candidate_usernames": candidate_users,
    })


@login_required
def add_dataset_access(request, slug):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return redirect("repository:detail", slug=slug)
    if request.method == "POST":
        from django.contrib.auth.models import User as AuthUser
        username = request.POST.get("username", "").strip()
        try:
            target = AuthUser.objects.get(username=username)
            if target == dataset.uploaded_by:
                messages.error(request, f"'{username}' is already the owner.")
            else:
                dataset.allowed_users.add(target)
                messages.success(request, f"'{username}' can now view this dataset.")
        except AuthUser.DoesNotExist:
            messages.error(request, f"No user with username '{username}'.")
    return redirect("repository:edit", slug=slug)


@login_required
def remove_dataset_access(request, slug, user_id):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return redirect("repository:detail", slug=slug)
    if request.method == "POST":
        dataset.allowed_users.remove(user_id)
    return redirect("repository:edit", slug=slug)


_BLANK = {"", "n/a", "na", "none", "null", "-"}


def _sort_key(val):
    v = (val or "").strip()
    if v.lower() in _BLANK:
        return (0, 0.0, "\xff")
    try:
        return (0, float(v), "")
    except (ValueError, TypeError):
        return (1, 0.0, v.lower())


def _build_samples_qs(query, active_category, col_filters=None, user=None):
    """Return a filtered (but not yet evaluated) Sample queryset.
    col_filters: list of (col_name, contains_value) pairs.
    """
    visible_ids = _visible_datasets(user).values_list("id", flat=True)
    qs = Sample.objects.select_related("dataset").filter(dataset_id__in=visible_ids)
    if query:
        qs = qs.filter(
            Q(sample_id__icontains=query)
            | Q(dataset__title__icontains=query)
            | Q(values__value__icontains=query)
        ).distinct()
    if active_category:
        qs = qs.filter(dataset__category=active_category)
    for col, val in (col_filters or []):
        if col and val:
            qs = qs.filter(values__column__name__iexact=col, values__value__icontains=val)
    return qs


# DB-sortable fields — pushed to SQL ORDER BY, no Python sort needed
_DB_SORT = {"sample_id": "sample_id", "type": "dataset__category"}


def _apply_sort_and_build_rows(samples_qs, show_columns, col_unit_map, sort_col, sort_dir):
    """
    Apply ordering (DB-level where possible) and attach .row to each sample.
    Returns a plain list of Sample objects.
    """
    reverse = sort_dir == "desc"

    if sort_col in _DB_SORT:
        order = f"{'-' if reverse else ''}{_DB_SORT[sort_col]}"
        samples_qs = samples_qs.order_by(order)

    samples = list(samples_qs.prefetch_related("values__column"))

    for s in samples:
        val_map = {v.column.name: v.value for v in s.values.all()}
        s.row = [(val_map.get(col, ""), col_unit_map.get(col, "")) for col in show_columns]

    # Python sort only needed for column-value fields (numeric-aware)
    if sort_col not in _DB_SORT and sort_col in show_columns:
        idx = show_columns.index(sort_col)
        samples.sort(
            key=lambda s: _sort_key(s.row[idx][0]) if idx < len(s.row) else (1, 0.0, ""),
            reverse=reverse,
        )

    return samples


def _col_values_bulk(col_names, active_category):
    """
    Return {col_name_lower: [distinct non-empty values]} for multiple column
    names in a single DB query instead of one query per column.
    """
    filter_q = Q()
    for name in col_names:
        filter_q |= Q(column__name__iexact=name)
    qs = SampleValue.objects.filter(filter_q).exclude(value="")
    if active_category:
        qs = qs.filter(sample__dataset__category=active_category)
    result = {name.lower(): [] for name in col_names}
    seen = {name.lower(): set() for name in col_names}
    for row in qs.values("column__name", "value").order_by("column__name", "value"):
        key = row["column__name"].lower()
        if key in result and row["value"] not in seen[key]:
            result[key].append(row["value"])
            seen[key].add(row["value"])
    return result


def samples_view(request):
    query           = request.GET.get("q", "")
    active_category = request.GET.get("category", "")
    selected_cols   = request.GET.getlist("cols")
    fcol_raw        = request.GET.getlist("fcol")
    fval_raw        = request.GET.getlist("fval")
    sort_col        = request.GET.get("sort_col", "")
    sort_dir        = request.GET.get("sort_dir", "asc")
    page_sizes      = [25, 50, 100]
    try:
        per_page = int(request.GET.get("per_page", 25))
    except ValueError:
        per_page = 25
    if per_page not in page_sizes:
        per_page = 25
    try:
        page_num = int(request.GET.get("page", 1))
    except ValueError:
        page_num = 1

    # Zip fcol/fval lists into (col, val) pairs, dropping empty column names
    col_filter_pairs = [
        (c.strip(), v.strip())
        for c, v in zip(fcol_raw, fval_raw + [""] * len(fcol_raw))
        if c.strip()
    ]

    samples_qs = _build_samples_qs(query, active_category, col_filter_pairs, user=request.user)

    available_columns = []
    if active_category:
        available_columns = list(
            SampleColumn.objects.filter(dataset__category=active_category)
            .values_list("name", flat=True)
            .distinct()
            .order_by("name")
        )

    show_columns = [c for c in selected_cols if c in available_columns]

    col_unit_map = {}
    if show_columns:
        for row in (SampleColumn.objects
                    .filter(name__in=show_columns)
                    .exclude(unit="")
                    .values("name", "unit")):
            col_unit_map.setdefault(row["name"], row["unit"])

    show_cols_zip = [(col, col_unit_map.get(col, "")) for col in show_columns]

    all_samples = _apply_sort_and_build_rows(samples_qs, show_columns, col_unit_map, sort_col, sort_dir)
    total_results = len(all_samples)

    from django.core.paginator import Paginator
    paginator = Paginator(all_samples, per_page)
    page_obj = paginator.get_page(page_num)
    samples = list(page_obj)

    category_values = (
        _visible_datasets(request.user).filter(samples__isnull=False)
        .order_by()
        .values_list("category", flat=True)
        .distinct()
    )
    category_lookup = dict(Dataset.CATEGORY_CHOICES)
    categories_with_samples = [
        {"value": c, "label": category_lookup.get(c, c.title())}
        for c in sorted(category_values)
    ]

    # Pad to 5 slots for the template (always show 5 column filter inputs)
    NUM_COL_SLOTS = 4
    active_pairs = col_filter_pairs[:NUM_COL_SLOTS]
    col_filter_slots_padded = active_pairs + [("", "")] * (NUM_COL_SLOTS - len(active_pairs))

    # All column names across visible datasets (for JS autocomplete)
    all_column_names = list(
        SampleColumn.objects
        .filter(dataset__in=_visible_datasets(request.user))
        .values_list("name", flat=True)
        .distinct()
        .order_by("name")
    )

    adv_active = bool(active_category or show_columns or col_filter_pairs)

    return render(request, "repository/samples.html", {
        "samples": samples,
        "page_obj": page_obj,
        "per_page": per_page,
        "page_sizes": page_sizes,
        "show_columns": show_columns,
        "show_cols_zip": show_cols_zip,
        "available_columns": available_columns,
        "query": query,
        "active_category": active_category,
        "categories_with_samples": categories_with_samples,
        "total_results": total_results,
        "col_filter_slots_padded": col_filter_slots_padded,
        "all_column_names": all_column_names,
        "adv_active": adv_active,
        "sort_col": sort_col,
        "sort_dir": sort_dir,
    })


def column_values_view(request):
    """AJAX: distinct non-empty values for a given column (for filter dropdown/autocomplete)."""
    col_name = request.GET.get("column", "").strip()
    category = request.GET.get("category", "").strip()
    if not col_name:
        return JsonResponse({"values": []})
    ds_qs = _visible_datasets(request.user)
    if category:
        ds_qs = ds_qs.filter(category=category)
    raw = (SampleValue.objects
           .filter(column__name=col_name, column__dataset__in=ds_qs)
           .exclude(value="")
           .values_list("value", flat=True)[:500])
    return JsonResponse({"values": sorted(set(raw))})


def samples_suggest_view(request):
    """AJAX: autocomplete suggestions for the main samples search bar."""
    q = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    if len(q) < 2:
        return JsonResponse({"samples": [], "columns": [], "values": [], "types": []})
    ds_qs = _visible_datasets(request.user)
    if category:
        ds_qs = ds_qs.filter(category=category)
    # Experiment types
    from repository.models import Dataset as _DS
    types = [
        {"value": val, "label": label}
        for val, label in _DS.CATEGORY_CHOICES
        if q.lower() in label.lower()
    ]
    # Sample IDs
    sample_rows = (Sample.objects
                   .filter(dataset__in=ds_qs, sample_id__icontains=q)
                   .select_related("dataset")[:8])
    samples = [{"id": s.sample_id, "slug": s.dataset.slug} for s in sample_rows]
    # Column names (deduplicated)
    col_rows = (SampleColumn.objects
                .filter(dataset__in=ds_qs, name__icontains=q)
                .values("name", "unit").distinct()[:20])
    seen_cols, columns = set(), []
    for c in col_rows:
        if c["name"] not in seen_cols and len(columns) < 8:
            seen_cols.add(c["name"])
            columns.append({"name": c["name"], "unit": c["unit"] or ""})
    # Unique column values
    val_rows = (SampleValue.objects
                .filter(column__dataset__in=ds_qs, value__icontains=q)
                .exclude(value="")
                .values("column__name", "value").distinct()[:30])
    seen_vals, values = set(), []
    for v in val_rows:
        key = (v["column__name"], v["value"])
        if key not in seen_vals and len(values) < 8:
            seen_vals.add(key)
            values.append({"column": v["column__name"], "value": v["value"]})
    return JsonResponse({"samples": samples, "columns": columns, "values": values, "types": types})


def samples_csv_view(request):
    """Return the currently-filtered + sorted samples table as a CSV download."""
    query           = request.GET.get("q", "")
    active_category = request.GET.get("category", "")
    selected_cols   = request.GET.getlist("cols")
    fcol_raw        = request.GET.getlist("fcol")
    fval_raw        = request.GET.getlist("fval")
    sort_col        = request.GET.get("sort_col", "")
    sort_dir        = request.GET.get("sort_dir", "asc")

    col_filter_pairs = [
        (c.strip(), v.strip())
        for c, v in zip(fcol_raw, fval_raw + [""] * len(fcol_raw))
        if c.strip()
    ]

    samples_qs = _build_samples_qs(query, active_category, col_filter_pairs, user=request.user)

    available_columns = []
    if active_category:
        available_columns = list(
            SampleColumn.objects.filter(dataset__category=active_category)
            .values_list("name", flat=True).distinct().order_by("name")
        )

    show_columns = [c for c in selected_cols if c in available_columns]

    col_unit_map = {}
    if show_columns:
        for row in (SampleColumn.objects
                    .filter(name__in=show_columns)
                    .exclude(unit="")
                    .values("name", "unit")):
            col_unit_map.setdefault(row["name"], row["unit"])

    samples = _apply_sort_and_build_rows(samples_qs, show_columns, col_unit_map, sort_col, sort_dir)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="samples.csv"'
    writer = csv.writer(response)

    header = ["Sample ID", "Type"]
    for col in show_columns:
        unit = col_unit_map.get(col, "")
        header.append(f"{col} [{unit}]" if unit else col)
    writer.writerow(header)

    for s in samples:
        row = [s.sample_id, s.dataset.get_category_display()]
        for val, _unit in s.row:
            row.append(val)
        writer.writerow(row)

    return response


def docs_view(request):
    page, _ = DocsPage.objects.get_or_create(pk=1, defaults={"title": "Documentation", "content": ""})
    if request.method == "POST":
        if not (request.user.is_authenticated and request.user.is_staff):
            from django.http import Http404
            raise Http404
        action = request.POST.get("action", "update_intro")
        if action == "update_intro":
            page.title = request.POST.get("title", page.title).strip() or page.title
            page.content = request.POST.get("content", "").strip()
            page.save()
            messages.success(request, "Docs page updated.")
        elif action == "add_section":
            DocsSection.objects.create(
                tab=request.POST.get("tab", "overview"),
                heading=request.POST.get("heading", "New Section").strip(),
                body=request.POST.get("body", "").strip(),
                rows=request.POST.get("rows", "").strip(),
                is_list=bool(request.POST.get("is_list")),
                order=int(request.POST.get("order", 99) or 99),
            )
            messages.success(request, "Section added.")
        elif action == "update_section":
            sec = get_object_or_404(DocsSection, pk=request.POST.get("section_pk"))
            sec.tab     = request.POST.get("tab", sec.tab)
            sec.heading = request.POST.get("heading", sec.heading).strip() or sec.heading
            sec.body    = request.POST.get("body", "").strip()
            sec.rows    = request.POST.get("rows", "").strip()
            sec.is_list = bool(request.POST.get("is_list"))
            sec.order   = int(request.POST.get("order", sec.order) or sec.order)
            sec.save()
            messages.success(request, "Section updated.")
        elif action == "delete_section":
            get_object_or_404(DocsSection, pk=request.POST.get("section_pk")).delete()
            messages.success(request, "Section deleted.")
        return redirect(reverse("repository:docs") + "?edit=1")
    edit_open = request.GET.get("edit") == "1"
    sections = list(DocsSection.objects.all())
    overview_sections = [s for s in sections if s.tab == DocsSection.TAB_OVERVIEW]
    naming_sections   = [s for s in sections if s.tab == DocsSection.TAB_NAMING]
    columns_sections  = [s for s in sections if s.tab == DocsSection.TAB_COLUMNS]
    return render(request, "repository/docs.html", {
        "page": page,
        "edit_open": edit_open,
        "overview_sections": overview_sections,
        "naming_sections": naming_sections,
        "columns_sections": columns_sections,
    })


@login_required
def upload_dataset_photo(request, slug):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return redirect("repository:detail", slug=slug)
    if request.method == "POST":
        img = request.FILES.get("photo") or request.FILES.get("image")
        if img:
            caption = request.POST.get("caption", "").strip()
            order = dataset.overview_photos.count()
            DatasetPhoto.objects.create(dataset=dataset, image=_to_web_image(img), caption=caption, order=order)
    return redirect(reverse("repository:detail", kwargs={"slug": slug}))


@login_required
def delete_dataset_photo(request, slug, photo_pk):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return redirect("repository:detail", slug=slug)
    photo = get_object_or_404(DatasetPhoto, pk=photo_pk, dataset=dataset)
    photo.delete()
    return redirect(reverse("repository:detail", kwargs={"slug": slug}))


def about_view(request):
    page, _ = AboutPage.objects.get_or_create(pk=1, defaults={"title": "About", "content": ""})
    if request.method == "POST":
        if not (request.user.is_authenticated and request.user.is_staff):
            from django.http import Http404
            raise Http404
        action = request.POST.get("action")
        if action == "update_content":
            page.title = request.POST.get("title", page.title).strip() or page.title
            page.content = request.POST.get("content", "").strip()
            page.save()
            messages.success(request, "About page updated.")
        elif action == "upload_photo":
            img = request.FILES.get("image")
            is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"
            if img:
                caption = request.POST.get("caption", "").strip()
                order = AboutPhoto.objects.filter(page=page).count()
                AboutPhoto.objects.create(page=page, image=_to_web_image(img), caption=caption, order=order)
                if is_ajax:
                    return JsonResponse({"ok": True})
                messages.success(request, "Photo uploaded.")
            else:
                if is_ajax:
                    return JsonResponse({"ok": False, "error": "No image selected."}, status=400)
                messages.error(request, "No image selected.")
        return redirect(reverse("repository:about") + "?edit=1")
    edit_open = request.GET.get("edit") == "1"
    return render(request, "repository/about.html", {"page": page, "photos": page.photos.all(), "edit_open": edit_open})


def about_photo_delete(request, pk):
    if not (request.user.is_authenticated and request.user.is_staff):
        from django.http import Http404
        raise Http404
    photo = get_object_or_404(AboutPhoto, pk=pk)
    if request.method == "POST":
        photo.image.delete(save=False)
        photo.delete()
        messages.success(request, "Photo deleted.")
    return redirect(reverse("repository:about") + "?edit=1")


def _staff_required(view_fn):
    """Decorator: 404 for non-staff users."""
    from functools import wraps
    @wraps(view_fn)
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_staff):
            from django.http import Http404
            raise Http404
        return view_fn(request, *args, **kwargs)
    return wrapper


@_staff_required
def todo_view(request):
    import json
    todos = list(TodoItem.objects.all())
    todos_json = json.dumps([{"id": t.pk, "text": t.text, "done": t.done} for t in todos])
    return render(request, "repository/todo.html", {"todos": todos, "todos_json": todos_json})


@_staff_required
def todo_add(request):
    if request.method == "POST":
        import json
        data = json.loads(request.body)
        text = data.get("text", "").strip()
        if text:
            order = TodoItem.objects.count()
            item = TodoItem.objects.create(text=text, order=order)
            return JsonResponse({"id": item.pk, "text": item.text, "done": item.done})
    return JsonResponse({"error": "bad request"}, status=400)


@_staff_required
def todo_toggle(request, pk):
    if request.method == "POST":
        item = get_object_or_404(TodoItem, pk=pk)
        item.done = not item.done
        item.save(update_fields=["done"])
        return JsonResponse({"id": item.pk, "done": item.done})
    return JsonResponse({"error": "bad request"}, status=400)


@_staff_required
def todo_edit(request, pk):
    if request.method == "POST":
        import json
        data = json.loads(request.body)
        text = data.get("text", "").strip()
        if text:
            item = get_object_or_404(TodoItem, pk=pk)
            item.text = text
            item.save(update_fields=["text"])
            return JsonResponse({"id": item.pk, "text": item.text})
    return JsonResponse({"error": "bad request"}, status=400)


@_staff_required
def todo_delete(request, pk):
    if request.method == "POST":
        TodoItem.objects.filter(pk=pk).delete()
        return JsonResponse({"ok": True})
    return JsonResponse({"error": "bad request"}, status=400)


@_staff_required
def todo_clear_done(request):
    if request.method == "POST":
        TodoItem.objects.filter(done=True).delete()
        return JsonResponse({"ok": True})
    return JsonResponse({"error": "bad request"}, status=400)


def _format_bytes(size):
    if size < 1024:
        return f"{size} B"
    elif size < 1024 ** 2:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 ** 3:
        return f"{size / 1024 ** 2:.1f} MB"
    return f"{size / 1024 ** 3:.1f} GB"
