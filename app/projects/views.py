import datetime
from django.db import models
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from app.accounts.models import UserAccount
from .models import (
    Project,
    Document,
    ServiceWorkflowTemplate,
    ProjectPhase,
    ProjectTask,
    ProjectStaffAssignment,
)
from .permissions import (
    IsProjectOwnerOrAdmin,
    IsAdminOnly,
    IsTaskAssigneeOrAdmin,
    IsQAReviewerOrAdmin,
)
from .serializers import (
    FileUploadSerializer,
    ProjectCreateSerializer,
    ProjectDetailSerializer,
    DocumentSerializer,
    ProjectListSerializer,
    ProjectUpdateSerializer,
    ServiceWorkflowTemplateSerializer,
    WorkflowPreviewRequestSerializer,
    ProjectCreateFromWorkflowSerializer,
    ProjectTaskSerializer,
    ProjectTaskUpdateSerializer,
    QAReviewActionSerializer,
)
from .workflow_engine import (
    generate_workflow_preview,
    create_project_from_workflow,
    get_active_staff_with_workload,
)


class ProjectListCreateView(APIView):
    """
    List user projects or create a new project.

    - Clients: View their own projects.
    - Admins, Super Admins, QA Reviewers: View all projects.
    - Staff: View only projects they are assigned to.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request: Request) -> Response:
        user = request.user
        if user.is_admin_user or user.role == UserAccount.Role.QA_REVIEWER:
            queryset = Project.objects.all()
        elif user.role == UserAccount.Role.STAFF:
            # Staff see only assigned projects
            queryset = Project.objects.filter(
                models.Q(staff_assignments__staff=user)
                | models.Q(tasks__assigned_to=user)
            ).distinct()
        else:
            # Clients see only their own projects
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
            project = Project.objects.prefetch_related(
                "documents",
                "phases__tasks__assigned_to",
                "staff_assignments__staff",
            ).get(pk=pk)
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


class ServiceWorkflowListView(APIView):
    """
    List all available predefined service workflow templates.
    Used by the Admin Project Creation wizard.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        templates = ServiceWorkflowTemplate.objects.filter(is_active=True).prefetch_related(
            "phase_templates__task_templates"
        )
        serializer = ServiceWorkflowTemplateSerializer(templates, many=True)
        return Response(
            {
                "success": True,
                "count": templates.count(),
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class ProjectWorkflowPreviewView(APIView):
    """
    Generate an interactive workflow preview before database persistence:
    Calculates phases, tasks, due dates, and auto-assigned staff by role and workload.
    Restricted to Admins and Super Admins.
    """

    permission_classes = [IsAuthenticated, IsAdminOnly]

    def post(self, request: Request) -> Response:
        serializer = WorkflowPreviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        service_slug = data.get("service_slug", "").strip()
        service_id = data.get("service_workflow_template_id")
        template = None
        if service_slug:
            template = ServiceWorkflowTemplate.objects.filter(slug=service_slug, is_active=True).first()
            if not template:
                try:
                    template = ServiceWorkflowTemplate.objects.filter(id=service_slug, is_active=True).first()
                except Exception:
                    pass
        if not template and service_id:
            template = ServiceWorkflowTemplate.objects.filter(id=service_id, is_active=True).first()

        if not template:
            return Response(
                {"detail": f"Service template '{service_slug or service_id}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        start_date = data.get("start_date") or timezone.now().date()
        client_name = data.get("client_name") or ""
        project_name = data.get("project_name") or None

        # If client_id provided, look up organization name
        if data.get("client_id") and not client_name:
            client_user = UserAccount.objects.filter(id=data["client_id"]).first()
            if client_user:
                client_name = client_user.full_name or client_user.email.split("@")[0]

        preview = generate_workflow_preview(
            service_template=template,
            start_date=start_date,
            custom_project_name=project_name,
            client_name=client_name,
        )

        return Response(
            {
                "success": True,
                "data": preview,
            },
            status=status.HTTP_200_OK,
        )


class ProjectCreateFromWorkflowView(APIView):
    """
    Create one or more Projects from predefined service workflow templates.
    If the Admin selects multiple services, creates distinct, separate projects for each.
    Restricted to Admins and Super Admins.
    """

    permission_classes = [IsAuthenticated, IsAdminOnly]

    def post(self, request: Request) -> Response:
        serializer = ProjectCreateFromWorkflowSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        client_user = UserAccount.objects.filter(id=data["client_id"]).first()
        if not client_user:
            return Response(
                {"detail": "Specified client user not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        company_name = data.get("company_name")
        if not company_name:
            company_name = client_user.full_name or client_user.email.split("@")[0]

        start_date = data.get("start_date") or timezone.now().date()
        service_slugs = data["service_slugs"]
        staff_overrides = data.get("staff_overrides") or {}
        custom_tasks = data.get("custom_tasks") or []
        custom_name = data.get("project_name") or ""
        description = data.get("description") or ""

        created_projects = []

        for idx, slug in enumerate(service_slugs):
            template = ServiceWorkflowTemplate.objects.filter(slug=slug, is_active=True).first()
            if not template:
                try:
                    template = ServiceWorkflowTemplate.objects.filter(id=slug, is_active=True).first()
                except Exception:
                    pass
            if not template:
                continue

            # Only use custom_name if single service was selected, otherwise prefix service
            p_name = None
            if len(service_slugs) == 1 and custom_name:
                p_name = custom_name
            elif custom_name:
                p_name = f"{custom_name} ({template.name})"

            project = create_project_from_workflow(
                client_user=client_user,
                service_template=template,
                start_date=start_date,
                company_name=company_name,
                project_name=p_name,
                description=description,
                staff_overrides=staff_overrides,
                custom_tasks=custom_tasks if idx == 0 else [],
                created_by_admin=request.user,
            )
            created_projects.append(project)

        if not created_projects:
            return Response(
                {"detail": "No valid service templates found for the provided slugs."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        output_serializer = ProjectListSerializer(created_projects, many=True, context={"request": request})

        return Response(
            {
                "success": True,
                "message": f"Successfully created {len(created_projects)} project(s) from service workflow.",
                "count": len(created_projects),
                "data": output_serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )


class StaffDirectoryForProjectsView(APIView):
    """
    Returns active staff and admin members with their functional roles and workload.
    Used for staff reassignment dropdowns in the Admin wizard.
    """

    permission_classes = [IsAuthenticated, IsAdminOnly]

    def get(self, request: Request) -> Response:
        staff_list = get_active_staff_with_workload()
        return Response(
            {
                "success": True,
                "count": len(staff_list),
                "data": staff_list,
            },
            status=status.HTTP_200_OK,
        )


class ClientDirectoryForProjectsView(APIView):
    """
    Returns list of clients for the Admin project creation selector.
    """

    permission_classes = [IsAuthenticated, IsAdminOnly]

    def get(self, request: Request) -> Response:
        clients = UserAccount.objects.filter(role=UserAccount.Role.CLIENT, is_active=True).order_by("email")
        data = []
        for c in clients:
            comp_name = "Valley Medical Center" if c.email == "client@gmail.com" else (c.job_title or c.full_name or c.username or "Healthcare Organization")
            client_name = c.full_name or f"{c.first_name} {c.last_name}".strip() or (c.username or c.email.split("@")[0].capitalize())
            data.append({
                "id": str(c.id),
                "email": c.email,
                "name": client_name,
                "company_name": comp_name,
            })
        return Response(
            {
                "success": True,
                "count": len(data),
                "data": data,
            },
            status=status.HTTP_200_OK,
        )


class ProjectTaskDetailUpdateView(APIView):
    """
    Staff member updates task status, deliverables, or notes and submits for QA review.
    """

    permission_classes = [IsAuthenticated, IsTaskAssigneeOrAdmin]

    def patch(self, request: Request, pk: str) -> Response:
        task = ProjectTask.objects.filter(pk=pk).first()
        if not task:
            return Response({"detail": "Task not found."}, status=status.HTTP_404_NOT_FOUND)

        self.check_object_permissions(request, task)

        serializer = ProjectTaskUpdateSerializer(task, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_task = serializer.save()

        # If staff submits for QA, update qa_status
        if updated_task.status == ProjectTask.TaskStatus.SUBMITTED_FOR_QA:
            updated_task.qa_status = ProjectTask.QAStatus.UNDER_REVIEW
            updated_task.save(update_fields=["qa_status", "updated_at"])

        return Response(
            {
                "success": True,
                "message": "Task updated successfully.",
                "data": ProjectTaskSerializer(updated_task).data,
            },
            status=status.HTTP_200_OK,
        )


class ProjectTaskQAReviewView(APIView):
    """
    QA Reviewer approves task submission or requests changes.
    """

    permission_classes = [IsAuthenticated, IsQAReviewerOrAdmin]

    def post(self, request: Request, pk: str) -> Response:
        task = ProjectTask.objects.filter(pk=pk).first()
        if not task:
            return Response({"detail": "Task not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = QAReviewActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data["action"]
        notes = serializer.validated_data.get("notes", "")

        if action == "approve":
            task.status = ProjectTask.TaskStatus.COMPLETED
            task.qa_status = ProjectTask.QAStatus.APPROVED
            task.qa_notes = notes
            task.qa_reviewer = request.user
            task.save(update_fields=["status", "qa_status", "qa_notes", "qa_reviewer", "updated_at"])
            message = "Task approved and marked completed."
        else:
            task.status = ProjectTask.TaskStatus.CHANGES_REQUESTED
            task.qa_status = ProjectTask.QAStatus.CHANGES_REQUESTED
            task.qa_notes = notes
            task.qa_reviewer = request.user
            task.save(update_fields=["status", "qa_status", "qa_notes", "qa_reviewer", "updated_at"])
            message = "Changes requested and assigned staff notified."

        return Response(
            {
                "success": True,
                "message": message,
                "data": ProjectTaskSerializer(task).data,
            },
            status=status.HTTP_200_OK,
        )

