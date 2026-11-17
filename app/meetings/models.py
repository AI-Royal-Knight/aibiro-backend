import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from app.common.models import BaseModel


def default_weekly_availability():
    return {
        "monday": [{"start": "09:00", "end": "17:00"}],
        "tuesday": [{"start": "09:00", "end": "17:00"}],
        "wednesday": [{"start": "09:00", "end": "17:00"}],
        "thursday": [{"start": "09:00", "end": "17:00"}],
        "friday": [{"start": "09:00", "end": "16:00"}],
        "saturday": [],
        "sunday": [],
    }


def default_durations():
    return [15, 30, 45, 60]


class AvailabilitySchedule(BaseModel):
    """
    Calendar availability configuration managed by the Admin/Operations Manager.
    Defines available days, time ranges, buffer periods, blackout dates, and notice rules.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="availability_schedules",
        help_text="The Admin or Operations Manager who owns this schedule",
    )
    name = models.CharField(
        max_length=150,
        default="Standard AccrediSure Availability",
        help_text="Name of the availability schedule profile",
    )
    timezone = models.CharField(
        max_length=60,
        default="America/New_York",
        help_text="Primary timezone (e.g. America/New_York, EST)",
    )
    meeting_durations = models.JSONField(
        default=default_durations,
        help_text="List of allowed meeting duration options in minutes (e.g. [15, 30, 45, 60])",
    )
    default_duration = models.PositiveIntegerField(
        default=30,
        help_text="Default meeting duration in minutes",
    )
    buffer_before_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Buffer time required before each meeting in minutes",
    )
    buffer_after_minutes = models.PositiveIntegerField(
        default=15,
        help_text="Buffer time required after each meeting in minutes to prevent back-to-back fatigue",
    )
    min_booking_notice_hours = models.PositiveIntegerField(
        default=2,
        help_text="Minimum advance notice required to book a meeting (e.g. 2 hours)",
    )
    min_cancel_notice_hours = models.PositiveIntegerField(
        default=4,
        help_text="Minimum notice required to reschedule or cancel a meeting without admin override",
    )
    weekly_availability = models.JSONField(
        default=default_weekly_availability,
        help_text="Weekly recurring available hours by day of week",
    )
    blackout_dates = models.JSONField(
        default=list,
        blank=True,
        help_text="List of specific unavailable dates with reasons (e.g. [{'date': '2026-12-25', 'reason': 'Holiday'}])",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this availability schedule is currently active for bookings",
    )

    class Meta:
        verbose_name = "Availability Schedule"
        verbose_name_plural = "Availability Schedules"
        ordering = ["-is_active", "-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.owner.email})"


class Meeting(BaseModel):
    """
    Scheduled meeting between Client and Admin/Operations Manager,
    optionally associated with a CMR Project, featuring Zoom integration and AI summary.
    """

    class MeetingStatus(models.TextChoices):
        SCHEDULED = "scheduled", _("Scheduled")
        RESCHEDULED = "rescheduled", _("Rescheduled")
        COMPLETED = "completed", _("Completed")
        CANCELED = "canceled", _("Canceled")

    class Initiator(models.TextChoices):
        CLIENT = "client", _("Client Initiated")
        ADMIN = "admin", _("Admin Initiated")

    class AISummaryStatus(models.TextChoices):
        NOT_STARTED = "not_started", _("Not Started")
        GENERATED = "generated", _("AI Generated (Pending Review)")
        APPROVED = "approved", _("Approved by Admin")

    title = models.CharField(
        max_length=255,
        default="AccrediSure Consulting Touchpoint",
        help_text="Meeting subject or topic",
    )
    host = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="hosted_meetings",
        help_text="Admin or Operations Manager hosting the session",
    )
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="client_meetings",
        help_text="Client participant",
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meetings",
        help_text="Applicable CMR project",
    )
    phase = models.ForeignKey(
        "projects.ProjectPhase",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meetings",
        help_text="Specific project phase if applicable",
    )
    start_time = models.DateTimeField(
        db_index=True,
        help_text="Meeting start timestamp (UTC)",
    )
    end_time = models.DateTimeField(
        db_index=True,
        help_text="Meeting end timestamp (UTC)",
    )
    duration_minutes = models.PositiveIntegerField(
        default=30,
        help_text="Duration in minutes",
    )
    timezone = models.CharField(
        max_length=60,
        default="America/New_York",
        help_text="Display timezone for participants",
    )
    status = models.CharField(
        max_length=30,
        choices=MeetingStatus.choices,
        default=MeetingStatus.SCHEDULED,
        db_index=True,
    )
    initiated_by = models.CharField(
        max_length=20,
        choices=Initiator.choices,
        default=Initiator.CLIENT,
    )

    # Client booking information
    purpose = models.TextField(
        help_text="Meeting reason, objective, or topic",
    )
    questions_concerns = models.TextField(
        blank=True,
        default="",
        help_text="Questions or concerns the client would like addressed",
    )
    notes = models.TextField(
        blank=True,
        default="",
        help_text="Additional notes or context provided before the meeting",
    )

    # Zoom Integration
    zoom_meeting_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Zoom Meeting ID",
    )
    zoom_join_url = models.URLField(
        max_length=500,
        blank=True,
        default="",
        help_text="URL for participants to join Zoom meeting",
    )
    zoom_start_url = models.URLField(
        max_length=1000,
        blank=True,
        default="",
        help_text="Host URL to start Zoom meeting",
    )
    zoom_passcode = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Meeting passcode",
    )
    zoom_recording_url = models.URLField(
        max_length=1000,
        blank=True,
        default="",
        help_text="Cloud recording replay URL",
    )
    zoom_transcript_url = models.URLField(
        max_length=1000,
        blank=True,
        default="",
        help_text="URL to full transcript file",
    )
    transcript_text = models.TextField(
        blank=True,
        default="",
        help_text="Full text transcript of the meeting discussion",
    )

    # AI Meeting Summary & CMR Integration
    ai_summary_status = models.CharField(
        max_length=30,
        choices=AISummaryStatus.choices,
        default=AISummaryStatus.NOT_STARTED,
    )
    ai_summary = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured AI meeting summary with purpose, discussion points, decisions, requests, recommendations, and action items",
    )
    admin_notes = models.TextField(
        blank=True,
        default="",
        help_text="Private notes for Admin/Operations Manager",
    )

    class Meta:
        verbose_name = "Meeting"
        verbose_name_plural = "Meetings"
        ordering = ["start_time"]
        indexes = [
            models.Index(fields=["host", "start_time"]),
            models.Index(fields=["client", "start_time"]),
            models.Index(fields=["status", "start_time"]),
            models.Index(fields=["project"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} - {self.client.email} ({self.start_time.strftime('%Y-%m-%d %H:%M')})"

    @property
    def is_upcoming(self) -> bool:
        return self.status in [self.MeetingStatus.SCHEDULED, self.MeetingStatus.RESCHEDULED] and self.end_time >= timezone.now()


class MeetingParticipant(BaseModel):
    """
    Participant in a scheduled meeting (Host, Client, or invited AccrediSure Staff Member).
    """

    class ParticipantRole(models.TextChoices):
        HOST = "host", _("Host (Operations Manager)")
        CLIENT = "client", _("Client")
        STAFF = "staff", _("AccrediSure Staff / Specialist")

    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="meeting_participations",
    )
    role = models.CharField(
        max_length=20,
        choices=ParticipantRole.choices,
        default=ParticipantRole.STAFF,
    )
    is_organizer = models.BooleanField(default=False)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="added_meeting_participants",
    )

    class Meta:
        verbose_name = "Meeting Participant"
        verbose_name_plural = "Meeting Participants"
        unique_together = ("meeting", "user")

    def __str__(self) -> str:
        return f"{self.user.email} ({self.role}) in {self.meeting.title}"


class MeetingHistory(BaseModel):
    """
    Immutable audit history log tracking meeting creation, rescheduling, cancellation, and task conversion.
    """

    class Action(models.TextChoices):
        SCHEDULED = "scheduled", _("Meeting Scheduled")
        RESCHEDULED = "rescheduled", _("Meeting Rescheduled")
        CANCELED = "canceled", _("Meeting Canceled")
        STAFF_ADDED = "staff_added", _("Staff Added")
        STAFF_REMOVED = "staff_removed", _("Staff Removed")
        SUMMARY_UPDATED = "summary_updated", _("AI Summary Reviewed/Updated")
        TASK_CONVERTED = "task_converted", _("Action Item Converted to CMR Task")

    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name="history",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meeting_actions",
    )
    action = models.CharField(
        max_length=40,
        choices=Action.choices,
    )
    previous_start_time = models.DateTimeField(null=True, blank=True)
    new_start_time = models.DateTimeField(null=True, blank=True)
    reason = models.TextField(blank=True, default="")
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Meeting History"
        verbose_name_plural = "Meeting Histories"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} on meeting {self.meeting_id} by {self.actor}"


class MeetingNotification(BaseModel):
    """
    In-app and email notification record dispatched for meeting events.
    """

    class NotificationType(models.TextChoices):
        BOOKING_CONFIRMATION = "booking_confirmation", _("Booking Confirmation")
        REMINDER_24H = "reminder_24h", _("24-Hour Reminder")
        REMINDER_1H = "reminder_1h", _("1-Hour Reminder")
        REMINDER_15M = "reminder_15m", _("15-Minute Reminder")
        RESCHEDULED = "rescheduled", _("Meeting Rescheduled")
        CANCELED = "canceled", _("Meeting Canceled")
        STAFF_INVITED = "staff_invited", _("Invited to Meeting")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="meeting_notifications",
    )
    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    notification_type = models.CharField(
        max_length=40,
        choices=NotificationType.choices,
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    sent_email = models.BooleanField(default=False)
    sent_sms = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Meeting Notification"
        verbose_name_plural = "Meeting Notifications"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.notification_type} for {self.user.email}"
