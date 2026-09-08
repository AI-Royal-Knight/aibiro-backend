from django.contrib import admin

from .models import Project, ProjectFile


class ProjectFileInline(admin.TabularInline):
    model = ProjectFile
    extra = 0
    readonly_fields = ("id", "original_name", "file_size", "content_type", "created_at")
    fields = ("id", "file", "original_name", "status", "file_size", "content_type", "uploaded_by", "created_at")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "company_name",
        "status",
        "compliance_score",
        "days_to_survey",
        "owner",
        "total_files",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("name", "company_name", "description", "owner__email")
    ordering = ("-created_at",)
    inlines = [ProjectFileInline]
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(ProjectFile)
class ProjectFileAdmin(admin.ModelAdmin):
    list_display = (
        "original_name",
        "project",
        "status",
        "file_size",
        "content_type",
        "uploaded_by",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("original_name", "project__name", "project__company_name", "uploaded_by__email")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "updated_at")
