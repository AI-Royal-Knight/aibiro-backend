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


class ProjectListSerializer(serializers.ModelSerializer):
    """
    Summary representation of a Project for list views.
    """

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    total_files = serializers.IntegerField(read_only=True)
    owner_email = serializers.EmailField(source="owner.email", read_only=True)

    class Meta:
        model = Project
        fields = (
            "id",
            "name",
            "company_name",
            "status",
            "status_display",
            "description",
            "compliance_score",
            "days_to_survey",
            "total_files",
            "owner",
            "owner_email",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ProjectDetailSerializer(serializers.ModelSerializer):
    """
    Detailed representation of a Project including all attached files.
    """

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    total_files = serializers.IntegerField(read_only=True)
    owner_email = serializers.EmailField(source="owner.email", read_only=True)
    files = DocumentSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = (
            "id",
            "name",
            "company_name",
            "status",
            "status_display",
            "description",
            "compliance_score",
            "days_to_survey",
            "total_files",
            "owner",
            "owner_email",
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
