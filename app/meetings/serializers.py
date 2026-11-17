from rest_framework import serializers
from app.accounts.models import UserAccount
from app.projects.models import Project, ProjectPhase
from .models import (
    AvailabilitySchedule,
    Meeting,
    MeetingParticipant,
    MeetingHistory,
    MeetingNotification,
)


class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAccount
        fields = ["id", "email", "full_name", "role", "job_title", "functional_roles"]


class AvailabilityScheduleSerializer(serializers.ModelSerializer):
    owner_details = UserSummarySerializer(source="owner", read_only=True)

    class Meta:
        model = AvailabilitySchedule
        fields = [
            "id",
            "owner",
            "owner_details",
            "name",
            "timezone",
            "meeting_durations",
            "default_duration",
            "buffer_before_minutes",
            "buffer_after_minutes",
            "min_booking_notice_hours",
            "min_cancel_notice_hours",
            "weekly_availability",
            "blackout_dates",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "owner", "created_at", "updated_at"]


class MeetingParticipantSerializer(serializers.ModelSerializer):
    user_details = UserSummarySerializer(source="user", read_only=True)

    class Meta:
        model = MeetingParticipant
        fields = [
            "id",
            "user",
            "user_details",
            "role",
            "is_organizer",
            "added_by",
            "created_at",
        ]


class MeetingHistorySerializer(serializers.ModelSerializer):
    actor_details = UserSummarySerializer(source="actor", read_only=True)

    class Meta:
        model = MeetingHistory
        fields = [
            "id",
            "actor",
            "actor_details",
            "action",
            "previous_start_time",
            "new_start_time",
            "reason",
            "details",
            "created_at",
        ]


class MeetingListSerializer(serializers.ModelSerializer):
    host_details = UserSummarySerializer(source="host", read_only=True)
    client_details = UserSummarySerializer(source="client", read_only=True)
    participants = MeetingParticipantSerializer(many=True, read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True, default="")
    project_company = serializers.CharField(source="project.company_name", read_only=True, default="")
    phase_name = serializers.CharField(source="phase.name", read_only=True, default="")

    class Meta:
        model = Meeting
        fields = [
            "id",
            "title",
            "host",
            "host_details",
            "client",
            "client_details",
            "project",
            "project_name",
            "project_company",
            "phase",
            "phase_name",
            "start_time",
            "end_time",
            "duration_minutes",
            "timezone",
            "status",
            "initiated_by",
            "purpose",
            "questions_concerns",
            "notes",
            "zoom_meeting_id",
            "zoom_join_url",
            "zoom_start_url",
            "zoom_passcode",
            "participants",
            "is_upcoming",
            "ai_summary_status",
            "created_at",
            "updated_at",
        ]


class MeetingDetailSerializer(MeetingListSerializer):
    history = MeetingHistorySerializer(many=True, read_only=True)

    class Meta(MeetingListSerializer.Meta):
        fields = MeetingListSerializer.Meta.fields + [
            "zoom_recording_url",
            "zoom_transcript_url",
            "transcript_text",
            "ai_summary",
            "admin_notes",
            "history",
        ]


class MeetingBookRequestSerializer(serializers.Serializer):
    start_time = serializers.DateTimeField()
    duration_minutes = serializers.IntegerField(default=30, min_value=15, max_value=240)
    client_id = serializers.UUIDField(required=False, allow_null=True)
    project_id = serializers.UUIDField(required=False, allow_null=True)
    phase_id = serializers.UUIDField(required=False, allow_null=True)
    title = serializers.CharField(required=False, allow_blank=True, default="AccrediSure Consulting Touchpoint")
    purpose = serializers.CharField(required=True)
    questions_concerns = serializers.CharField(required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    staff_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
    )


class MeetingRescheduleSerializer(serializers.Serializer):
    new_start_time = serializers.DateTimeField()
    duration_minutes = serializers.IntegerField(required=False, default=None)
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class MeetingCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class AddStaffSerializer(serializers.Serializer):
    staff_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
    )


class AISummaryUpdateSerializer(serializers.Serializer):
    ai_summary = serializers.DictField(required=True)
    admin_notes = serializers.CharField(required=False, allow_blank=True, default="")
    ai_summary_status = serializers.ChoiceField(
        choices=Meeting.AISummaryStatus.choices,
        required=False,
        default=Meeting.AISummaryStatus.APPROVED,
    )


class ConvertActionItemToTaskSerializer(serializers.Serializer):
    action_item_id = serializers.CharField(required=True)
    project_id = serializers.UUIDField(required=True)
    phase_id = serializers.UUIDField(required=False, allow_null=True)
    assigned_to_id = serializers.UUIDField(required=False, allow_null=True)
    title = serializers.CharField(required=False, allow_blank=True)
    due_date = serializers.DateField(required=False, allow_null=True)
    priority = serializers.CharField(required=False, default="Medium")
    responsible_role = serializers.CharField(required=False, default="Compliance Architect")


class MeetingNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeetingNotification
        fields = [
            "id",
            "meeting",
            "notification_type",
            "title",
            "message",
            "is_read",
            "sent_email",
            "sent_sms",
            "created_at",
        ]
