import os
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from app.common.models import BaseModel


class Project(BaseModel):
    """
    Project model for client accreditation, surveys, and audits.
    """

    class ProjectStatus(models.TextChoices):
        ACTIVE = "active", _("Active")
        IN_PROGRESS = "in_progress", _("In Progress")
        PENDING_REVIEW = "pending_review", _("Pending Review")
        COMPLETED = "completed", _("Completed")
        ARCHIVED = "archived", _("Archived")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="projects",
        help_text="The client or user who owns this project",
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
        return self.files.count()


class ProjectFile(BaseModel):
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
        related_name="files",
        help_text="The project this file belongs to",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_project_files",
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
        verbose_name = "Project File"
        verbose_name_plural = "Project Files"
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
