from django.urls import path

from .views import (
    ProjectDetailView,
    DocumentDetailView,
    DocumentUploadView,
    ProjectListCreateView,
)

urlpatterns = [
    path("", ProjectListCreateView.as_view(), name="project-list-create"),
    path("<uuid:pk>/", ProjectDetailView.as_view(), name="project-detail"),
    path("<uuid:project_id>/files/", DocumentUploadView.as_view(), name="project-documents"),
    path("<uuid:project_id>/files/<uuid:file_id>/", DocumentDetailView.as_view(), name="project-document-detail"),
]
