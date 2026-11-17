from django.urls import path

from .views import (
    ProjectDetailView,
    DocumentDetailView,
    DocumentUploadView,
    ProjectListCreateView,
    ServiceWorkflowListView,
    ProjectWorkflowPreviewView,
    ProjectCreateFromWorkflowView,
    StaffDirectoryForProjectsView,
    ClientDirectoryForProjectsView,
    ProjectTaskDetailUpdateView,
    ProjectTaskQAReviewView,
    BoardTaskListCreateView,
    BoardTaskDetailUpdateView,
)

urlpatterns = [
    path("", ProjectListCreateView.as_view(), name="project-list-create"),
    path("service-workflows/", ServiceWorkflowListView.as_view(), name="service-workflow-list"),
    path("preview-workflow/", ProjectWorkflowPreviewView.as_view(), name="project-workflow-preview"),
    path("create-from-workflow/", ProjectCreateFromWorkflowView.as_view(), name="project-create-from-workflow"),
    path("staff-directory/", StaffDirectoryForProjectsView.as_view(), name="project-staff-directory"),
    path("clients-directory/", ClientDirectoryForProjectsView.as_view(), name="project-clients-directory"),
    path("tasks/<uuid:pk>/", ProjectTaskDetailUpdateView.as_view(), name="project-task-update"),
    path("tasks/<uuid:pk>/qa-review/", ProjectTaskQAReviewView.as_view(), name="project-task-qa-review"),
    path("<uuid:pk>/", ProjectDetailView.as_view(), name="project-detail"),
    path("<uuid:project_id>/files/", DocumentUploadView.as_view(), name="project-documents"),
    path("<uuid:project_id>/files/<uuid:file_id>/", DocumentDetailView.as_view(), name="project-document-detail"),
    path("board-tasks/", BoardTaskListCreateView.as_view(), name="board-task-list"),
    path("board-tasks/<uuid:pk>/", BoardTaskDetailUpdateView.as_view(), name="board-task-detail"),
]

