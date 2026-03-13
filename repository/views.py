import csv

from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseRedirect, HttpResponse
from django.urls import reverse
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.db.models import Q, Count
from django.utils.http import url_has_allowed_host_and_scheme

from .models import Dataset, Tag, DataFile, Notebook, Sample, SampleColumn, SampleValue
from .forms import DatasetUploadForm, DataFileForm, NotebookForm

ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".xlsx", ".json", ".tiff", ".tif", ".zip", ".tsv", ".txt"}


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

    columns = list(dataset.sample_columns.all())
    samples = list(dataset.samples.prefetch_related("values").all())
    # Build row data from prefetch cache — avoids N×M individual queries
    for s in samples:
        val_map = {v.column_id: v.value for v in s.values.all()}
        s.row_with_cols = [(col, val_map.get(col.pk, "")) for col in columns]

    # Column names already used in other datasets of the same category (for suggestions)
    existing_col_names = list(
        SampleColumn.objects.filter(dataset__category=dataset.category)
        .exclude(dataset=dataset)
        .values_list("name", flat=True)
        .distinct()
        .order_by("name")
    )

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

    notebooks = list(dataset.notebooks.all())
    context = {
        "dataset": dataset,
        "notebooks": notebooks,
        "sample_columns": columns,
        "samples": samples,
        "suggested_column_names": existing_col_names,
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
                MAX_UPLOAD_BYTES = 150 * 1024 * 1024  # 150 MB
                if uploaded.size > MAX_UPLOAD_BYTES:
                    messages.error(request, "File exceeds the 150 MB maximum size limit.")
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
        elif uploaded.size > 150 * 1024 * 1024:
            messages.error(request, "File exceeds the 150 MB maximum size limit.")
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

@login_required
def add_notebook(request, slug):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return redirect("repository:detail", slug=slug)
    if dataset.notebooks.count() >= 3:
        messages.error(request, "Maximum of 3 notebook tabs per experiment.")
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
        nb.save()
        messages.success(request, f"Notebook tab '{tab_label}' added.")
        return redirect("repository:detail", slug=slug)
    return render(request, "repository/add_notebook.html", {"dataset": dataset})


@login_required
def delete_notebook(request, slug, pk):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return redirect("repository:detail", slug=slug)
    if request.method == "POST":
        Notebook.objects.filter(pk=pk, dataset=dataset).delete()
    return redirect("repository:detail", slug=slug)


@login_required
def add_sample_column(request, slug):
    dataset = get_object_or_404(Dataset, slug=slug)
    if not _can_edit(request.user, dataset):
        messages.error(request, "Permission denied.")
        return _redirect_to_tab(slug, "tab-samples")
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if name:
            order = dataset.sample_columns.count()
            SampleColumn.objects.get_or_create(dataset=dataset, name=name, defaults={"order": order})
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
    columns = list(dataset.sample_columns.all())
    if request.method == "POST":
        sample_id = request.POST.get("sample_id", "").strip()
        if sample_id:
            sample, _ = Sample.objects.get_or_create(dataset=dataset, sample_id=sample_id)
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
    columns = list(dataset.sample_columns.all())
    if request.method == "POST":
        sample_id = request.POST.get("sample_id", "").strip()
        if sample_id:
            sample.sample_id = sample_id
            sample.save()
            for col in columns:
                val = request.POST.get(f"col_{col.id}", "").strip()
                SampleValue.objects.update_or_create(
                    sample=sample, column=col, defaults={"value": val}
                )
            messages.success(request, f"Sample '{sample_id}' updated.")
        return _redirect_to_tab(slug, "tab-samples")
    current_values = {v.column_id: v.value for v in sample.values.all()}
    column_values = [(col, current_values.get(col.id, "")) for col in columns]
    return render(request, "repository/edit_sample.html", {
        "dataset": dataset,
        "sample": sample,
        "column_values": column_values,
    })


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
            sid_col = next(
                (h for h in headers if h.strip().lower() in ("sample_id", "sample id", "id")),
                headers[0] if headers else None,
            )
            data_headers = [h for h in headers if h != sid_col]

            # get_or_create columns (few per dataset, cheap)
            col_map = {}
            for h in data_headers:
                col, _ = SampleColumn.objects.get_or_create(
                    dataset=dataset, name=h,
                    defaults={"order": dataset.sample_columns.count()},
                )
                col_map[h] = col

            # Read all rows up-front
            rows = [r for r in reader if sid_col and r.get(sid_col, "").strip()]
            all_sids = [r[sid_col].strip() for r in rows]

            # Fetch existing samples in one query, bulk-create new ones
            existing_samples = {
                s.sample_id: s
                for s in Sample.objects.filter(dataset=dataset, sample_id__in=all_sids)
            }
            new_sids = [sid for sid in dict.fromkeys(all_sids) if sid not in existing_samples]
            if new_sids:
                Sample.objects.bulk_create(
                    [Sample(dataset=dataset, sample_id=sid) for sid in new_sids],
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

            to_create, to_update = [], []
            for row in rows:
                sid = row[sid_col].strip()
                sample = existing_samples.get(sid)
                if not sample:
                    continue
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
    return render(request, "repository/edit_dataset.html", {
        "form": form,
        "dataset": dataset,
        "allowed_users": allowed,
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


def _build_samples_qs(query, active_category, f_species, f_substrate, f_coating, user=None):
    """Return a filtered (but not yet evaluated) Sample queryset."""
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
    if f_species:
        qs = qs.filter(values__column__name__iexact="species", values__value=f_species)
    if f_substrate:
        qs = qs.filter(values__column__name__iexact="substrate", values__value=f_substrate)
    if f_coating:
        qs = qs.filter(values__column__name__iexact="coating", values__value=f_coating)
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
    f_species       = request.GET.get("filter_species", "")
    f_substrate     = request.GET.get("filter_substrate", "")
    f_coating       = request.GET.get("filter_coating", "")
    sort_col        = request.GET.get("sort_col", "")
    sort_dir        = request.GET.get("sort_dir", "asc")

    samples_qs = _build_samples_qs(query, active_category, f_species, f_substrate, f_coating, user=request.user)

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

    samples = _apply_sort_and_build_rows(samples_qs, show_columns, col_unit_map, sort_col, sort_dir)

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

    adv_filter_values = _col_values_bulk(["species", "substrate", "coating"], active_category)
    adv_active = bool(show_columns or f_species or f_substrate or f_coating)

    return render(request, "repository/samples.html", {
        "samples": samples,
        "show_columns": show_columns,
        "show_cols_zip": show_cols_zip,
        "available_columns": available_columns,
        "query": query,
        "active_category": active_category,
        "categories_with_samples": categories_with_samples,
        "total_results": len(samples),
        "f_species": f_species,
        "f_substrate": f_substrate,
        "f_coating": f_coating,
        "species_values": adv_filter_values["species"],
        "substrate_values": adv_filter_values["substrate"],
        "coating_values": adv_filter_values["coating"],
        "adv_active": adv_active,
        "sort_col": sort_col,
        "sort_dir": sort_dir,
    })


def samples_csv_view(request):
    """Return the currently-filtered + sorted samples table as a CSV download."""
    query           = request.GET.get("q", "")
    active_category = request.GET.get("category", "")
    selected_cols   = request.GET.getlist("cols")
    f_species       = request.GET.get("filter_species", "")
    f_substrate     = request.GET.get("filter_substrate", "")
    f_coating       = request.GET.get("filter_coating", "")
    sort_col        = request.GET.get("sort_col", "")
    sort_dir        = request.GET.get("sort_dir", "asc")

    samples_qs = _build_samples_qs(query, active_category, f_species, f_substrate, f_coating, user=request.user)

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
    return render(request, "repository/docs.html")


def _format_bytes(size):
    if size < 1024:
        return f"{size} B"
    elif size < 1024 ** 2:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 ** 3:
        return f"{size / 1024 ** 2:.1f} MB"
    return f"{size / 1024 ** 3:.1f} GB"
