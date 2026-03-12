from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.db.models import Q, Count
from django.utils.http import url_has_allowed_host_and_scheme

from .models import Dataset, Tag, DataFile, Notebook
from .forms import DatasetUploadForm, DataFileForm, NotebookForm

ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".xlsx", ".json", ".tiff", ".tif", ".zip", ".tsv", ".txt"}


def home(request):
    category  = request.GET.get("category", "")
    query     = request.GET.get("q", "")
    sort      = request.GET.get("sort", "date")
    order     = request.GET.get("order", "desc")
    f_species = request.GET.get("species", "")
    f_lab     = request.GET.get("lab", "")
    f_inst    = request.GET.get("institution", "")
    f_license = request.GET.get("license", "")

    datasets = Dataset.objects.prefetch_related("tags", "notebooks").all()

    if category and category != "all":
        datasets = datasets.filter(category=category)
    if query:
        datasets = datasets.filter(
            Q(title__icontains=query)
            | Q(abstract__icontains=query)
            | Q(species__icontains=query)
            | Q(tags__name__icontains=query)
        ).distinct()
    if f_species:
        datasets = datasets.filter(species=f_species)
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
    species_list     = Dataset.objects.exclude(species="").values_list("species", flat=True).distinct().order_by("species")
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
        "f_species": f_species,
        "f_lab": f_lab,
        "f_inst": f_inst,
        "f_license": f_license,
        "species_list": species_list,
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

    if request.method == "POST" and "download" in request.POST:
        dataset.download_count += 1
        dataset.save(update_fields=["download_count"])
        return redirect("repository:detail", slug=slug)

    context = {"dataset": dataset}
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
    f_species = request.GET.get("species", "")
    f_lab     = request.GET.get("lab", "")
    f_inst    = request.GET.get("institution", "")
    f_license = request.GET.get("license", "")

    sort_field = {"date": "created_at", "downloads": "download_count", "title": "title"}.get(sort, "created_at")
    order_prefix = "" if order == "asc" else "-"

    base_qs = Dataset.objects.prefetch_related("tags")
    if query:
        base_qs = base_qs.filter(
            Q(title__icontains=query)
            | Q(abstract__icontains=query)
            | Q(species__icontains=query)
            | Q(tags__name__icontains=query)
        ).distinct()
    if f_species:
        base_qs = base_qs.filter(species=f_species)
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

    species_list     = Dataset.objects.exclude(species="").values_list("species", flat=True).distinct().order_by("species")
    lab_list         = Dataset.objects.exclude(lab="").values_list("lab", flat=True).distinct().order_by("lab")
    institution_list = Dataset.objects.exclude(institution="").values_list("institution", flat=True).distinct().order_by("institution")

    return render(request, "repository/collections.html", {
        "collections": collections,
        "total_results": total_results,
        "query": query,
        "sort": sort,
        "order": order,
        "active_category": category or "all",
        "f_species": f_species,
        "f_lab": f_lab,
        "f_inst": f_inst,
        "f_license": f_license,
        "species_list": species_list,
        "lab_list": lab_list,
        "institution_list": institution_list,
        "category_choices": Dataset.CATEGORY_CHOICES,
        "license_choices": Dataset.LICENSE_CHOICES,
        "sort_options": [("date", "Date"), ("downloads", "Downloads"), ("title", "Title")],
    })


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
