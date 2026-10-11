from django.urls import path
from web import views

urlpatterns = [
    path("", views.index, name="index"),
    path("run/", views.run_bot_view, name="run_bot"),
    path("download/<str:filename>/", views.download_file, name="download"),
]
