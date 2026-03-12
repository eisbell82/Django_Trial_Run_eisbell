from django.urls import path
from . import views

app_name = "repository"

urlpatterns = [
    path("", views.home, name="home"),
    path("datasets/<slug:slug>/", views.dataset_detail, name="detail"),
    path("upload/", views.upload_dataset, name="upload"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register_view, name="register"),
    path("collections/", views.collections_view, name="collections"),
    path("docs/", views.docs_view, name="docs"),
    path("datasets/<slug:slug>/delete/", views.delete_dataset, name="delete"),
]
