from django.urls import path
from .views import (
    AvailabilityScheduleView,
    AvailableSlotsView,
    MeetingAISummaryGenerateView,
    MeetingAISummaryUpdateView,
    MeetingAddStaffView,
    MeetingCancelView,
    MeetingConvertActionItemView,
    MeetingDetailView,
    MeetingListCreateView,
    MeetingNotificationListView,
    MeetingNotificationMarkReadView,
    MeetingRemoveStaffView,
    MeetingRescheduleView,
    TriggerDueRemindersView,
)

app_name = "meetings"

urlpatterns = [
    # Availability Configuration & Slots
    path("availability/", AvailabilityScheduleView.as_view(), name="availability-schedule"),
    path("available-slots/", AvailableSlotsView.as_view(), name="available-slots"),

    # Meetings Core
    path("", MeetingListCreateView.as_view(), name="meeting-list-create"),
    path("<uuid:pk>/", MeetingDetailView.as_view(), name="meeting-detail"),
    path("<uuid:pk>/reschedule/", MeetingRescheduleView.as_view(), name="meeting-reschedule"),
    path("<uuid:pk>/cancel/", MeetingCancelView.as_view(), name="meeting-cancel"),

    # Staff Management
    path("<uuid:pk>/add-staff/", MeetingAddStaffView.as_view(), name="meeting-add-staff"),
    path("<uuid:pk>/remove-staff/<uuid:staff_id>/", MeetingRemoveStaffView.as_view(), name="meeting-remove-staff"),

    # AI Recording & Summary & CMR Integration
    path("<uuid:pk>/generate-ai-summary/", MeetingAISummaryGenerateView.as_view(), name="meeting-generate-ai-summary"),
    path("<uuid:pk>/ai-summary/", MeetingAISummaryUpdateView.as_view(), name="meeting-ai-summary-update"),
    path("<uuid:pk>/convert-action-item/", MeetingConvertActionItemView.as_view(), name="meeting-convert-action-item"),

    # In-App Notifications
    path("notifications/", MeetingNotificationListView.as_view(), name="meeting-notifications"),
    path("notifications/<uuid:pk>/read/", MeetingNotificationMarkReadView.as_view(), name="meeting-notification-mark-read"),

    # Reminders Cron/Trigger
    path("trigger-reminders/", TriggerDueRemindersView.as_view(), name="trigger-reminders"),
]
