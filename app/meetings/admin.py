from django.contrib import admin
from .models import (
    AvailabilitySchedule,
    Meeting,
    MeetingParticipant,
    MeetingHistory,
    MeetingNotification,
)


class MeetingParticipantInline(admin.TabularInline):
    model = MeetingParticipant
    extra = 1


class MeetingHistoryInline(admin.TabularInline):
    model = MeetingHistory
    extra = 0
    readonly_fields = ["actor", "action", "previous_start_time", "new_start_time", "reason", "created_at"]


@admin.register(AvailabilitySchedule)
class AvailabilityScheduleAdmin(admin.ModelAdmin):
    list_display = ["name", "owner", "timezone", "default_duration", "buffer_after_minutes", "is_active"]
    list_filter = ["is_active", "timezone"]


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ["title", "client", "host", "project", "start_time", "duration_minutes", "status", "initiated_by"]
    list_filter = ["status", "initiated_by", "ai_summary_status"]
    search_fields = ["title", "purpose", "client__email", "client__full_name", "zoom_meeting_id"]
    inlines = [MeetingParticipantInline, MeetingHistoryInline]


@admin.register(MeetingNotification)
class MeetingNotificationAdmin(admin.ModelAdmin):
    list_display = ["title", "user", "notification_type", "is_read", "sent_email", "created_at"]
    list_filter = ["notification_type", "is_read", "sent_email"]
