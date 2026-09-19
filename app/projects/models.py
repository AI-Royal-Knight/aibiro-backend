import os
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from app.common.models import BaseModel


class ServiceWorkflowTemplate(BaseModel):
    """
    Predefined service workflow definition maintained by the system / Super Admin.
    Examples: CARF Initial Accreditation, State Licensing, Mock Survey Gap Analysis, etc.
    """

    class Category(models.TextChoices):
        ACCREDITATION_LICENSING = "accreditation-licensing", _("Accreditation & State Licensing")
        SURVEYS_AUDITS = "surveys-audits", _("Surveys & Audit Defense")
        POLICIES_CLINICAL = "policies-clinical", _("Policy & Clinical Manuals")
        GOVERNANCE_QUALITY = "governance-quality", _("Quality, Risk & Governance")
        OPERATIONS_REVENUE = "operations-revenue", _("Operations & Billing Readiness")

    name = models.CharField(max_length=255, help_text="e.g. Accreditation Preparation (Initial)")
    slug = models.SlugField(max_length=120, unique=True, help_text="Unique slug code (e.g. carf-initial)")
    category = models.CharField(max_length=50, choices=Category.choices, default=Category.ACCREDITATION_LICENSING)
    category_label = models.CharField(max_length=120, blank=True)
    tagline = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    duration_weeks = models.PositiveIntegerField(default=12, help_text="Expected delivery duration in weeks")
    programs = models.JSONField(default=list, blank=True, help_text="List of programs (e.g. OMHC, PRP)")
    standards_alignment = models.JSONField(default=list, blank=True)
    team_roles = models.JSONField(default=list, blank=True, help_text="List of required specialist roles")
    quote_range = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Service Workflow Template"
        verbose_name_plural = "Service Workflow Templates"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ServicePhaseTemplate(BaseModel):
    """
    Standard phase blueprint for a service workflow.
    """

    service_template = models.ForeignKey(
        ServiceWorkflowTemplate,
        on_delete=models.CASCADE,
        related_name="phase_templates",
    )
    phase_number = models.PositiveIntegerField(help_text="Sequence number (1, 2, 3...)")
    name = models.CharField(max_length=200, help_text="e.g. Discovery & Gap Analysis")
    objective = models.TextField(blank=True)
    responsible_role = models.CharField(max_length=100, default="Engagement Lead")
    week_start = models.PositiveIntegerField(default=1)
    week_end = models.PositiveIntegerField(default=2)

    class Meta:
        verbose_name = "Service Phase Template"
        verbose_name_plural = "Service Phase Templates"
        ordering = ["service_template", "phase_number"]
        unique_together = ("service_template", "phase_number")

    def __str__(self) -> str:
        return f"{self.service_template.slug} - Phase {self.phase_number}: {self.name}"


class ServiceTaskTemplate(BaseModel):
    """
    Standard task blueprint within a service phase.
    """

    phase_template = models.ForeignKey(
        ServicePhaseTemplate,
        on_delete=models.CASCADE,
        related_name="task_templates",
    )
    title = models.CharField(max_length=255)
    responsible_role = models.CharField(
        max_length=100,
        default="Compliance Architect",
        help_text="Functional role required (e.g. Policy Specialist, Compliance Architect)",
    )
    deliverables = models.JSONField(default=list, blank=True, help_text="List of key deliverables for this task")
    relative_due_week = models.PositiveIntegerField(default=1, help_text="Week offset from project start")
    order = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Service Task Template"
        verbose_name_plural = "Service Task Templates"
        ordering = ["phase_template", "order"]

    def __str__(self) -> str:
        return f"{self.phase_template.name} - Task: {self.title} ({self.responsible_role})"


class Project(BaseModel):
    """
    Project model for client accreditation, surveys, and audits.
    """

    class ProjectStatus(models.TextChoices):
        ACTIVE = "active", _("Active")
        IN_PROGRESS = "in_progress", _("In Progress")
        PENDING = "pending", _("Pending")
        COMPLETED = "completed", _("Completed")
        DELAYED = "delayed", _("Delayed")
        ARCHIVED = "archived", _("Archived")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="projects",
        help_text="The client or user who owns this project",
    )
    service_template = models.ForeignKey(
        ServiceWorkflowTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projects",
        help_text="Predefined service template from which this project was generated",
    )
    name = models.CharField(
        max_length=200,
        help_text="Project or survey name (e.g. CARF Accreditation Survey)",
    )
    company_name = models.CharField(
        max_length=200,
        help_text="Organization or company name (e.g. Horizon Behavioral)",
    )
    status = models.CharField(
        max_length=30,
        choices=ProjectStatus.choices,
        default=ProjectStatus.ACTIVE,
        help_text="Current lifecycle status of the project",
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Optional background or scope description",
    )
    start_date = models.DateField(
        null=True,
        blank=True,
        help_text="Project commencement date",
    )
    target_end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Calculated or customized completion deadline",
    )
    compliance_score = models.PositiveIntegerField(
        default=0,
        blank=True,
        null=True,
        help_text="Compliance score percentage (0-100)",
    )
    days_to_survey = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Remaining days until accreditation survey",
    )

    class Meta:
        verbose_name = "Project"
        verbose_name_plural = "Projects"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["company_name"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.company_name})"

    @property
    def total_files(self) -> int:
        return self.documents.count()

    @property
    def files(self):
        """Backward compatibility alias for self.documents"""
        return self.documents



class Document(BaseModel):
    """
    File or document uploaded under a Project.
    Supports any file type (PDF, DOCX, XLSX, images, archives, text, etc.).
    """

    class FileStatus(models.TextChoices):
        PENDING_REVIEW = "pending_review", _("Pending AI Review")
        REVIEWED = "reviewed", _("Reviewed")
        FLAGGED = "flagged", _("Flagged")
        APPROVED = "approved", _("Approved")

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="documents",
        help_text="The project this file belongs to",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_documents",
    )
    file = models.FileField(
        upload_to="projects/files/%Y/%m/",
        help_text="The uploaded file asset",
    )
    original_name = models.CharField(
        max_length=255,
        help_text="Original uploaded filename with extension",
    )
    file_size = models.PositiveBigIntegerField(
        default=0,
        help_text="File size in bytes",
    )
    content_type = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="MIME content type (e.g. application/pdf)",
    )
    status = models.CharField(
        max_length=30,
        choices=FileStatus.choices,
        default=FileStatus.PENDING_REVIEW,
        help_text="Review/audit status of the document",
    )

    class Meta:
        verbose_name = "Document"
        verbose_name_plural = "Documents"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.original_name} ({self.project.name})"

    @property
    def extension(self) -> str:
        _, ext = os.path.splitext(self.original_name)
        return ext.lower().lstrip(".")


class ProjectPhase(BaseModel):
    """
    Realized phase of a client project.
    """

    class PhaseStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        IN_PROGRESS = "in_progress", _("In Progress")
        COMPLETED = "completed", _("Completed")

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="phases",
    )
    phase_template = models.ForeignKey(
        ServicePhaseTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="instantiated_phases",
    )
    phase_number = models.PositiveIntegerField(default=1)
    name = models.CharField(max_length=200)
    objective = models.TextField(blank=True, default="")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=30,
        choices=PhaseStatus.choices,
        default=PhaseStatus.PENDING,
    )

    class Meta:
        verbose_name = "Project Phase"
        verbose_name_plural = "Project Phases"
        ordering = ["project", "phase_number"]

    def __str__(self) -> str:
        return f"{self.project.name} - Phase {self.phase_number}: {self.name}"

    @property
    def total_tasks(self) -> int:
        return self.tasks.count()

    @property
    def completed_tasks(self) -> int:
        return self.tasks.filter(status=ProjectTask.TaskStatus.COMPLETED).count()


class ProjectTask(BaseModel):
    """
    Concrete task within a ProjectPhase, assigned to a staff member.
    """

    class TaskStatus(models.TextChoices):
        TODO = "todo", _("To Do")
        IN_PROGRESS = "in_progress", _("In Progress")
        SUBMITTED_FOR_QA = "submitted_for_qa", _("Submitted for QA")
        CHANGES_REQUESTED = "changes_requested", _("Changes Requested")
        APPROVED = "approved", _("Approved by QA")
        COMPLETED = "completed", _("Completed")

    class QAStatus(models.TextChoices):
        NOT_SUBMITTED = "not_submitted", _("Not Submitted")
        UNDER_REVIEW = "under_review", _("Under Review")
        CHANGES_REQUESTED = "changes_requested", _("Changes Requested")
        APPROVED = "approved", _("Approved")

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    phase = models.ForeignKey(
        ProjectPhase,
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    task_template = models.ForeignKey(
        ServiceTaskTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="instantiated_tasks",
    )
    title = models.CharField(max_length=255)
    responsible_role = models.CharField(
        max_length=100,
        help_text="Required consulting role (e.g. Compliance Architect)",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_project_tasks",
    )
    due_date = models.DateField(null=True, blank=True)
    deliverables = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=30,
        choices=TaskStatus.choices,
        default=TaskStatus.TODO,
    )
    priority = models.CharField(max_length=20, default="Medium")
    submission_notes = models.TextField(blank=True, default="")
    qa_notes = models.TextField(blank=True, default="")
    qa_status = models.CharField(
        max_length=30,
        choices=QAStatus.choices,
        default=QAStatus.NOT_SUBMITTED,
    )
    qa_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_tasks",
    )
    is_custom = models.BooleanField(
        default=False,
        help_text="True if added manually by Admin rather than from standard template",
    )
    order = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Project Task"
        verbose_name_plural = "Project Tasks"
        ordering = ["phase", "order", "created_at"]

    def __str__(self) -> str:
        return f"{self.project.name} - {self.title}"


class ProjectStaffAssignment(BaseModel):
    """
    Designated staff member and their functional role on a project.
    """

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="staff_assignments",
    )
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_assignments",
    )
    role_assigned = models.CharField(max_length=100, help_text="e.g. Engagement Lead, Compliance Architect")
    is_lead = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Project Staff Assignment"
        verbose_name_plural = "Project Staff Assignments"
        unique_together = ("project", "staff", "role_assigned")

    def __str__(self) -> str:
        return f"{self.staff.email} as {self.role_assigned} on {self.project.name}"
