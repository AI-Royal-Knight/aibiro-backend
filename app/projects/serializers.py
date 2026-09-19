import os
from rest_framework import serializers

from .models import Project, Document


class DocumentSerializer(serializers.ModelSerializer):
    """
    Representation of an uploaded project file/document.
    """

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    extension = serializers.CharField(read_only=True)
    file_size_formatted = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    uploaded_by_email = serializers.EmailField(source="uploaded_by.email", read_only=True)

    class Meta:
        model = Document
        fields = (
            "id",
            "project",
            "file",
            "file_url",
            "original_name",
            "file_size",
            "file_size_formatted",
            "content_type",
            "status",
            "status_display",
            "extension",
            "uploaded_by",
            "uploaded_by_email",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "project",
            "file_url",
            "original_name",
            "file_size",
            "file_size_formatted",
            "content_type",
            "status_display",
            "extension",
            "uploaded_by",
            "uploaded_by_email",
            "created_at",
            "updated_at",
        )

    def get_file_url(self, obj: Document) -> str:
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return ""

    def get_file_size_formatted(self, obj: Document) -> str:
        size = obj.file_size or 0
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}".replace(".0", "")
            size /= 1024.0
        return f"{size:.1f} TB"


from app.accounts.models import UserAccount
from .models import (
    Project,
    Document,
    ServiceWorkflowTemplate,
    ServicePhaseTemplate,
    ServiceTaskTemplate,
    ProjectPhase,
    ProjectTask,
    ProjectStaffAssignment,
)


class ServiceTaskTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceTaskTemplate
        fields = (
            "id",
            "title",
            "responsible_role",
            "deliverables",
            "relative_due_week",
            "order",
        )


class ServicePhaseTemplateSerializer(serializers.ModelSerializer):
    tasks = ServiceTaskTemplateSerializer(source="task_templates", many=True, read_only=True)

    class Meta:
        model = ServicePhaseTemplate
        fields = (
            "id",
            "phase_number",
            "name",
            "objective",
            "responsible_role",
            "week_start",
            "week_end",
            "tasks",
        )


class ServiceWorkflowTemplateSerializer(serializers.ModelSerializer):
    phases = ServicePhaseTemplateSerializer(source="phase_templates", many=True, read_only=True)
    category_display = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = ServiceWorkflowTemplate
        fields = (
            "id",
            "name",
            "slug",
            "category",
            "category_display",
            "category_label",
            "tagline",
            "description",
            "duration_weeks",
            "programs",
            "standards_alignment",
            "team_roles",
            "quote_range",
            "is_active",
            "phases",
        )


class ProjectTaskSerializer(serializers.ModelSerializer):
    assigned_to_email = serializers.EmailField(source="assigned_to.email", read_only=True)
    assigned_to_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    qa_status_display = serializers.CharField(source="get_qa_status_display", read_only=True)

    class Meta:
        model = ProjectTask
        fields = (
            "id",
            "project",
            "phase",
            "title",
            "responsible_role",
            "assigned_to",
            "assigned_to_email",
            "assigned_to_name",
            "due_date",
            "deliverables",
            "status",
            "status_display",
            "priority",
            "submission_notes",
            "qa_notes",
            "qa_status",
            "qa_status_display",
            "is_custom",
            "order",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def get_assigned_to_name(self, obj: ProjectTask) -> str:
        if not obj.assigned_to:
            return "Unassigned"
        return (
            obj.assigned_to.full_name
            or f"{obj.assigned_to.first_name} {obj.assigned_to.last_name}".strip()
            or obj.assigned_to.email.split("@")[0]
        )


class ProjectPhaseSerializer(serializers.ModelSerializer):
    tasks = ProjectTaskSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    total_tasks = serializers.IntegerField(read_only=True)
    completed_tasks = serializers.IntegerField(read_only=True)

    class Meta:
        model = ProjectPhase
        fields = (
            "id",
            "project",
            "phase_number",
            "name",
            "objective",
            "start_date",
            "end_date",
            "status",
            "status_display",
            "total_tasks",
            "completed_tasks",
            "tasks",
        )


class ProjectStaffAssignmentSerializer(serializers.ModelSerializer):
    staff_email = serializers.EmailField(source="staff.email", read_only=True)
    staff_name = serializers.SerializerMethodField()
    staff_job_title = serializers.CharField(source="staff.job_title", read_only=True)

    class Meta:
        model = ProjectStaffAssignment
        fields = (
            "id",
            "project",
            "staff",
            "staff_email",
            "staff_name",
            "staff_job_title",
            "role_assigned",
            "is_lead",
        )

    def get_staff_name(self, obj: ProjectStaffAssignment) -> str:
        return (
            obj.staff.full_name
            or f"{obj.staff.first_name} {obj.staff.last_name}".strip()
            or obj.staff.email.split("@")[0]
        )


class ProjectListSerializer(serializers.ModelSerializer):
    """
    Summary representation of a Project for list views.
    """

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    total_files = serializers.IntegerField(read_only=True)
    owner_email = serializers.EmailField(source="owner.email", read_only=True)
    service_name = serializers.CharField(source="service_template.name", read_only=True)
    service_slug = serializers.CharField(source="service_template.slug", read_only=True)
    current_phase = serializers.SerializerMethodField()
    assigned_staff_summary = serializers.SerializerMethodField()
    progress_percentage = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = (
            "id",
            "name",
            "company_name",
            "service_template",
            "service_name",
            "service_slug",
            "status",
            "status_display",
            "description",
            "start_date",
            "target_end_date",
            "compliance_score",
            "days_to_survey",
            "total_files",
            "current_phase",
            "progress_percentage",
            "assigned_staff_summary",
            "owner",
            "owner_email",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_current_phase(self, obj: Project) -> str:
        active_phase = obj.phases.filter(status=ProjectPhase.PhaseStatus.IN_PROGRESS).first()
        if active_phase:
            return f"Phase {active_phase.phase_number}: {active_phase.name}"
        first_phase = obj.phases.first()
        if first_phase:
            return f"Phase {first_phase.phase_number}: {first_phase.name}"
        return "Phase 1: Initial Setup"

    def get_assigned_staff_summary(self, obj: Project) -> str:
        names = []
        for sa in obj.staff_assignments.select_related("staff")[:3]:
            n = sa.staff.full_name or sa.staff.email.split("@")[0]
            names.append(n)
        return ", ".join(names) if names else "Staff Assigned"

    def get_progress_percentage(self, obj: Project) -> int:
        total = obj.tasks.count()
        if total == 0:
            return 0
        completed = obj.tasks.filter(status=ProjectTask.TaskStatus.COMPLETED).count()
        return int((completed / total) * 100)


class ProjectDetailSerializer(serializers.ModelSerializer):
    """
    Detailed representation of a Project including all attached files,
    instantiated phases, tasks, and staff assignments.
    """

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    total_files = serializers.IntegerField(read_only=True)
    owner_email = serializers.EmailField(source="owner.email", read_only=True)
    service_name = serializers.CharField(source="service_template.name", read_only=True)
    service_slug = serializers.CharField(source="service_template.slug", read_only=True)
    files = DocumentSerializer(source="documents", many=True, read_only=True)
    phases = ProjectPhaseSerializer(many=True, read_only=True)
    staff_assignments = ProjectStaffAssignmentSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = (
            "id",
            "name",
            "company_name",
            "service_template",
            "service_name",
            "service_slug",
            "status",
            "status_display",
            "description",
            "start_date",
            "target_end_date",
            "compliance_score",
            "days_to_survey",
            "total_files",
            "owner",
            "owner_email",
            "phases",
            "staff_assignments",
            "files",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ProjectCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a new Project.
    Strictly requires: `name`, `company_name`, `status`.
    Optionally accepts an uploaded file or multiple files during creation.
    """

    name = serializers.CharField(
        max_length=200,
        required=True,
        trim_whitespace=True,
        error_messages={"required": "Project name is required."},
    )
    company_name = serializers.CharField(
        max_length=200,
        required=True,
        trim_whitespace=True,
        error_messages={"required": "Company name is required."},
    )
    status = serializers.ChoiceField(
        choices=Project.ProjectStatus.choices,
        required=True,
        error_messages={"required": "Project status is required."},
    )
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )
    compliance_score = serializers.IntegerField(
        required=False,
        min_value=0,
        max_value=100,
        default=0,
    )
    days_to_survey = serializers.IntegerField(
        required=False,
        min_value=0,
        allow_null=True,
        default=None,
    )

    class Meta:
        model = Project
        fields = (
            "id",
            "name",
            "company_name",
            "status",
            "description",
            "compliance_score",
            "days_to_survey",
        )
        read_only_fields = ("id",)

    def create(self, validated_data: dict) -> Project:
        request = self.context.get("request")
        user = request.user if request else None
        project = Project.objects.create(owner=user, **validated_data)

        # Handle optional initial file attachment(s) if provided in multipart request
        if request and request.FILES:
            for file_key in request.FILES:
                for uploaded_file in request.FILES.getlist(file_key):
                    Document.objects.create(
                        project=project,
                        uploaded_by=user,
                        file=uploaded_file,
                        original_name=uploaded_file.name,
                        file_size=uploaded_file.size,
                        content_type=getattr(uploaded_file, "content_type", "") or "",
                    )

        return project


class ProjectUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating all fields of an existing Project.
    Allows updating: name, company_name, status, description, compliance_score, days_to_survey.
    """

    name = serializers.CharField(
        max_length=200,
        required=False,
        trim_whitespace=True,
    )
    company_name = serializers.CharField(
        max_length=200,
        required=False,
        trim_whitespace=True,
    )
    status = serializers.ChoiceField(
        choices=Project.ProjectStatus.choices,
        required=False,
    )
    description = serializers.CharField(
        required=False,
        allow_blank=True,
    )
    compliance_score = serializers.IntegerField(
        required=False,
        min_value=0,
        max_value=100,
    )
    days_to_survey = serializers.IntegerField(
        required=False,
        min_value=0,
        allow_null=True,
    )

    class Meta:
        model = Project
        fields = (
            "id",
            "name",
            "company_name",
            "status",
            "description",
            "compliance_score",
            "days_to_survey",
        )
        read_only_fields = ("id",)


class FileUploadSerializer(serializers.Serializer):
    """
    Serializer for uploading any file type under an existing Project.
    """

    file = serializers.FileField(
        required=True,
        error_messages={"required": "A file must be provided for upload."},
    )
    status = serializers.ChoiceField(
        choices=Document.FileStatus.choices,
        required=False,
        default=Document.FileStatus.PENDING_REVIEW,
    )

    def save(self, project: Project, user) -> Document:
        uploaded_file = self.validated_data["file"]
        status_value = self.validated_data.get(
            "status",
            Document.FileStatus.PENDING_REVIEW,
        )

        document = Document.objects.create(
            project=project,
            uploaded_by=user,
            file=uploaded_file,
            original_name=uploaded_file.name,
            file_size=uploaded_file.size,
            content_type=getattr(uploaded_file, "content_type", "") or "",
            status=status_value,
        )
        return document


class WorkflowPreviewRequestSerializer(serializers.Serializer):
    """
    Request serializer to simulate/preview a workflow before creation.
    """

    service_slug = serializers.CharField(required=False, allow_blank=True, default="")
    service_workflow_template_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    client_id = serializers.UUIDField(required=False, allow_null=True)
    client_name = serializers.CharField(required=False, allow_blank=True, default="")
    project_name = serializers.CharField(required=False, allow_blank=True, default="")
    start_date = serializers.DateField(required=False, default=serializers.CreateOnlyDefault(default=None))


class ProjectCreateFromWorkflowSerializer(serializers.Serializer):
    """
    Admin submission to create 1 or more projects from selected service templates.
    """

    client_id = serializers.UUIDField(
        required=True,
        help_text="Target client user UUID",
    )
    company_name = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Organization name (defaults to client user's full name or email)",
    )
    service_slugs = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False,
        help_text="List of service slugs (e.g. ['carf-initial', 'mock-survey']). Creates 1 project per service.",
    )
    start_date = serializers.DateField(
        required=False,
        default=None,
        help_text="Project start date. Defaults to today.",
    )
    project_name = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Optional custom name (only used if single service is selected)",
    )
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )
    staff_overrides = serializers.DictField(
        required=False,
        default=dict,
        help_text="Mapping of { 'Functional Role': 'user-uuid' } for admin reassignment",
    )
    custom_tasks = serializers.ListField(
        required=False,
        default=list,
        help_text="Optional list of custom tasks to add during creation",
    )


class ProjectTaskUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for staff to update task progress, notes, deliverables, and submit for QA.
    """

    class Meta:
        model = ProjectTask
        fields = (
            "id",
            "title",
            "due_date",
            "status",
            "priority",
            "deliverables",
            "submission_notes",
            "assigned_to",
        )
        read_only_fields = ("id", "title")


class QAReviewActionSerializer(serializers.Serializer):
    """
    Serializer for QA reviewer to approve or request changes on a submitted task.
    """

    action = serializers.ChoiceField(
        choices=["approve", "request_changes"],
        required=True,
    )
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )

