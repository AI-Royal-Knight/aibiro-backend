from django.urls import path

from .views import (
    ProjectDetailView,
    ProjectFileDetailView,
    ProjectFileUploadView,
    ProjectListCreateView,
)

urlpatterns = [
    path("", ProjectListCreateView.as_view(), name="project-list-create"),
    path("<uuid:pk>/", ProjectDetailView.as_view(), name="project-detail"),
    path("<uuid:project_id>/files/", ProjectFileUploadView.as_view(), name="project-files"),
    path("<uuid:project_id>/files/<uuid:file_id>/", ProjectFileDetailView.as_view(), name="project-file-detail"),
]
