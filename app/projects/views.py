from django.db import models
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from app.accounts.models import UserAccount
from .models import Project, Document
from .permissions import IsProjectOwnerOrAdmin
from .serializers import (
    FileUploadSerializer,
    ProjectCreateSerializer,
    ProjectDetailSerializer,
    DocumentSerializer,
    ProjectListSerializer,
    ProjectUpdateSerializer,
)


class ProjectListCreateView(APIView):
    """
    List user projects or create a new project.

    - Clients: View their own projects.
    - Admins, Super Admins, Staff, QA Reviewers: View all projects.
    - Project Creation requires: `name`, `company_name`, and `status`.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request: Request) -> Response:
        user = request.user
        if user.is_admin_user or user.role in (UserAccount.Role.STAFF, UserAccount.Role.QA_REVIEWER):
            queryset = Project.objects.all()
        else:
            queryset = Project.objects.filter(owner=user)

        # Filters
        status_param = request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param.lower().strip())

        search_param = request.query_params.get("search")
        if search_param:
            search_param = search_param.strip()
            queryset = queryset.filter(
                models.Q(name__icontains=search_param)
                | models.Q(company_name__icontains=search_param)
                | models.Q(description__icontains=search_param)
            )

        queryset = queryset.order_by("-created_at")
        serializer = ProjectListSerializer(queryset, many=True, context={"request": request})
        return Response(
            {
                "success": True,
                "count": queryset.count(),
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request: Request) -> Response:
        serializer = ProjectCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        project = serializer.save()

        detail_serializer = ProjectDetailSerializer(project, context={"request": request})
        return Response(
            {
                "success": True,
                "message": "Project created successfully.",
                "data": detail_serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )


class ProjectDetailView(APIView):
    """
    Retrieve, update all fields, or delete a specific Project.
    """

    permission_classes = [IsAuthenticated, IsProjectOwnerOrAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_object(self, pk: str) -> Project:
        try:
            project = Project.objects.prefetch_related("files").get(pk=pk)
        except (Project.DoesNotExist, ValueError):
            raise Project.DoesNotExist

        self.check_object_permissions(self.request, project)
        return project

    def get(self, request: Request, pk: str) -> Response:
        try:
            project = self.get_object(pk)
        except Project.DoesNotExist:
            return Response(
                {"detail": "Project not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = ProjectDetailSerializer(project, context={"request": request})
        return Response(
            {
                "success": True,
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request: Request, pk: str) -> Response:
        """Full update of all project fields."""
        try:
            project = self.get_object(pk)
        except Project.DoesNotExist:
            return Response(
                {"detail": "Project not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = ProjectUpdateSerializer(
            project,
            data=request.data,
            partial=False,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        updated_project = serializer.save()

        return Response(
            {
                "success": True,
                "message": "Project updated successfully.",
                "data": ProjectDetailSerializer(updated_project, context={"request": request}).data,
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request: Request, pk: str) -> Response:
        """Partial update of project fields."""
        try:
            project = self.get_object(pk)
        except Project.DoesNotExist:
            return Response(
                {"detail": "Project not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = ProjectUpdateSerializer(
            project,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        updated_project = serializer.save()

        return Response(
            {
                "success": True,
                "message": "Project updated successfully.",
                "data": ProjectDetailSerializer(updated_project, context={"request": request}).data,
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request: Request, pk: str) -> Response:
        try:
            project = self.get_object(pk)
        except Project.DoesNotExist:
            return Response(
                {"detail": "Project not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        project.delete()
        return Response(
            {
                "success": True,
                "message": "Project deleted successfully.",
            },
            status=status.HTTP_204_NO_CONTENT,
        )


class DocumentUploadView(APIView):
    """
    List files or upload any type of file under a project.
    """

    permission_classes = [IsAuthenticated, IsProjectOwnerOrAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def get_project(self, project_id: str) -> Project:
        try:
            project = Project.objects.get(pk=project_id)
        except (Project.DoesNotExist, ValueError):
            raise Project.DoesNotExist

        self.check_object_permissions(self.request, project)
        return project

    def get(self, request: Request, project_id: str) -> Response:
        """List all files attached to this project."""
        try:
            project = self.get_project(project_id)
        except Project.DoesNotExist:
            return Response(
                {"detail": "Project not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        files = project.files.all().order_by("-created_at")
        serializer = DocumentSerializer(files, many=True, context={"request": request})
        return Response(
            {
                "success": True,
                "count": files.count(),
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request: Request, project_id: str) -> Response:
        """Upload any file (PDF, DOCX, XLSX, images, text, archives, etc.) under the project."""
        try:
            project = self.get_project(project_id)
        except Project.DoesNotExist:
            return Response(
                {"detail": "Project not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not request.FILES:
            return Response(
                {"file": ["No file was submitted."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Handle multiple files if uploaded together
        uploaded_records = []
        status_value = request.data.get("status", Document.FileStatus.PENDING_REVIEW)
        if status_value not in Document.FileStatus.values:
            status_value = Document.FileStatus.PENDING_REVIEW

        for key in request.FILES:
            for raw_file in request.FILES.getlist(key):
                file_record = Document.objects.create(
                    project=project,
                    uploaded_by=request.user,
                    file=raw_file,
                    original_name=raw_file.name,
                    file_size=raw_file.size,
                    content_type=getattr(raw_file, "content_type", "") or "",
                    status=status_value,
                )
                uploaded_records.append(file_record)

        if len(uploaded_records) == 1:
            data = DocumentSerializer(uploaded_records[0], context={"request": request}).data
        else:
            data = DocumentSerializer(uploaded_records, many=True, context={"request": request}).data

        return Response(
            {
                "success": True,
                "message": f"{len(uploaded_records)} file(s) uploaded successfully.",
                "data": data,
            },
            status=status.HTTP_201_CREATED,
        )


class DocumentDetailView(APIView):
    """
    Retrieve, update status, or delete an uploaded file from a project.
    """

    permission_classes = [IsAuthenticated, IsProjectOwnerOrAdmin]

    def get_file_and_project(self, project_id: str, file_id: str) -> tuple[Project, Document]:
        try:
            project = Project.objects.get(pk=project_id)
            self.check_object_permissions(self.request, project)
            document = project.files.get(pk=file_id)
            return project, document
        except (Project.DoesNotExist, Document.DoesNotExist, ValueError):
            raise Document.DoesNotExist

    def get(self, request: Request, project_id: str, file_id: str) -> Response:
        try:
            _, document = self.get_file_and_project(project_id, file_id)
        except Document.DoesNotExist:
            return Response(
                {"detail": "File not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = DocumentSerializer(document, context={"request": request})
        return Response(
            {
                "success": True,
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request: Request, project_id: str, file_id: str) -> Response:
        """Update file status (e.g. reviewed, flagged, approved)."""
        try:
            _, document = self.get_file_and_project(project_id, file_id)
        except Document.DoesNotExist:
            return Response(
                {"detail": "File not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        new_status = request.data.get("status")
        if new_status:
            if new_status not in Document.FileStatus.values:
                return Response(
                    {"status": [f"Invalid status. Choose from: {list(Document.FileStatus.values)}"]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            document.status = new_status
            document.save(update_fields=["status", "updated_at"])

        serializer = DocumentSerializer(document, context={"request": request})
        return Response(
            {
                "success": True,
                "message": "File status updated successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request: Request, project_id: str, file_id: str) -> Response:
        try:
            _, document = self.get_file_and_project(project_id, file_id)
        except Document.DoesNotExist:
            return Response(
                {"detail": "File not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        document.delete()
        return Response(
            {
                "success": True,
                "message": "File deleted successfully.",
            },
            status=status.HTTP_204_NO_CONTENT,
        )
