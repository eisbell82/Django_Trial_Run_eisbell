from django.urls import path
from . import views

app_name = "repository"

urlpatterns = [
    path("", views.home, name="home"),
    path("datasets/<slug:slug>/", views.dataset_detail, name="detail"),
    path("upload/", views.upload_dataset, name="upload"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
]
