from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.utils.http import url_has_allowed_host_and_scheme

from .models import Dataset, Tag, DataFile, Notebook
from .forms import DatasetUploadForm, DataFileForm, NotebookForm

ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".xlsx", ".json", ".tiff", ".tif", ".zip", ".tsv", ".txt"}


def home(request):
    category = request.GET.get("category", "")
    query = request.GET.get("q", "")

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

    stats = Dataset.objects.aggregate(
        total_count=Count("id"),
        notebook_count=Count("notebooks"),
        contributor_count=Count("uploaded_by", distinct=True),
    )

    context = {
        "datasets": datasets,
        "total_count": stats["total_count"],
        "notebook_count": stats["notebook_count"],
        "contributor_count": stats["contributor_count"],
        "active_category": category or "all",
        "query": query,
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
    logout(request)
    return redirect("repository:home")


def _format_bytes(size):
    if size < 1024:
        return f"{size} B"
    elif size < 1024 ** 2:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 ** 3:
        return f"{size / 1024 ** 2:.1f} MB"
    return f"{size / 1024 ** 3:.1f} GB"
