import logging
from datetime import timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import Meeting, MeetingNotification, MeetingParticipant

logger = logging.getLogger(__name__)


def send_notification(user, meeting: Meeting, notification_type: str, title: str, message: str):
    """
    Creates an in-app MeetingNotification record and dispatches an email.
    """
    # 1. In-App Notification
    notif = MeetingNotification.objects.create(
        user=user,
        meeting=meeting,
        notification_type=notification_type,
        title=title,
        message=message,
    )

    # 2. Email Notification
    recipient_email = user.email
    if recipient_email:
        try:
            subject = f"[AccrediSure] {title}"
            from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@midgeneration.com")
            
            # Formatted email body
            body = f"""Dear {user.full_name or user.email.split('@')[0]},

{message}

Meeting Details:
• Title: {meeting.title}
• Date & Time: {meeting.start_time.strftime('%A, %B %d, %Y at %I:%M %p UTC')}
• Duration: {meeting.duration_minutes} minutes
• Join Zoom Meeting: {meeting.zoom_join_url}
• Meeting ID: {meeting.zoom_meeting_id}
• Passcode: {meeting.zoom_passcode}

You can also manage or view this session directly on your AccrediSure dashboard.

Best regards,
AccrediSure Operations Team
"""
            send_mail(
                subject=subject,
                message=body,
                from_email=from_email,
                recipient_list=[recipient_email],
                fail_silently=True,
            )
            notif.sent_email = True
            notif.save(update_fields=["sent_email"])
        except Exception as e:
            logger.warning(f"Failed to send email to {recipient_email}: {e}")

    return notif


def notify_booking_confirmation(meeting: Meeting):
    """
    Sends immediate confirmation to host, client, and any participants.
    """
    # Notify Client
    client_title = f"Meeting Confirmed: {meeting.title}"
    client_msg = (
        f"Your consultation with AccrediSure Operations has been confirmed for "
        f"{meeting.start_time.strftime('%B %d, %Y at %I:%M %p UTC')}. "
        f"Zoom meeting information has been generated and added to your dashboard."
    )
    send_notification(meeting.client, meeting, MeetingNotification.NotificationType.BOOKING_CONFIRMATION, client_title, client_msg)

    # Notify Host (Admin / Operations Manager)
    host_title = f"New Scheduled Meeting: {meeting.title} ({meeting.client.email})"
    host_msg = (
        f"A new meeting was booked by {meeting.client.full_name or meeting.client.email} for "
        f"{meeting.start_time.strftime('%B %d, %Y at %I:%M %p UTC')}. Purpose: {meeting.purpose}"
    )
    send_notification(meeting.host, meeting, MeetingNotification.NotificationType.BOOKING_CONFIRMATION, host_title, host_msg)


def notify_rescheduled(meeting: Meeting, actor, reason: str = ""):
    """
    Notifies all participants of a rescheduled time.
    """
    participants = MeetingParticipant.objects.filter(meeting=meeting).select_related("user")
    users = {p.user for p in participants}
    users.add(meeting.host)
    users.add(meeting.client)

    title = f"Meeting Rescheduled: {meeting.title}"
    reason_text = f" Reason: {reason}" if reason else ""
    msg = (
        f"The meeting has been rescheduled to {meeting.start_time.strftime('%B %d, %Y at %I:%M %p UTC')}.{reason_text} "
        f"The Zoom meeting room details remain accessible from your dashboard."
    )

    for user in users:
        send_notification(user, meeting, MeetingNotification.NotificationType.RESCHEDULED, title, msg)


def notify_canceled(meeting: Meeting, actor, reason: str = ""):
    """
    Notifies all participants of a cancellation.
    """
    participants = MeetingParticipant.objects.filter(meeting=meeting).select_related("user")
    users = {p.user for p in participants}
    users.add(meeting.host)
    users.add(meeting.client)

    title = f"Meeting Canceled: {meeting.title}"
    reason_text = f" Reason: {reason}" if reason else ""
    msg = (
        f"The meeting scheduled for {meeting.start_time.strftime('%B %d, %Y at %I:%M %p UTC')} "
        f"has been canceled by {actor.full_name or actor.email}.{reason_text}"
    )

    for user in users:
        send_notification(user, meeting, MeetingNotification.NotificationType.CANCELED, title, msg)


def notify_staff_added(meeting: Meeting, staff_user, added_by):
    """
    Notifies staff member added by Admin/Operations Manager.
    """
    title = f"Added to Meeting: {meeting.title}"
    msg = (
        f"You have been added to an upcoming client meeting by {added_by.full_name or added_by.email}. "
        f"Client: {meeting.client.full_name or meeting.client.email}. "
        f"Date: {meeting.start_time.strftime('%B %d, %Y at %I:%M %p UTC')}. "
        f"Purpose: {meeting.purpose}. Zoom information is available on your dashboard."
    )
    send_notification(staff_user, meeting, MeetingNotification.NotificationType.STAFF_INVITED, title, msg)


def process_due_reminders():
    """
    Scans upcoming meetings and sends 24h, 1h, and 15m reminders.
    Can be invoked via endpoint, management command, or periodic task.
    """
    now = timezone.now()
    active_meetings = Meeting.objects.filter(
        status__in=[Meeting.MeetingStatus.SCHEDULED, Meeting.MeetingStatus.RESCHEDULED],
        start_time__gt=now,
    )

    sent_count = 0

    for m in active_meetings:
        time_until_start = m.start_time - now
        
        # 1. 24-hour reminder (between 23h and 25h)
        if timedelta(hours=23) <= time_until_start <= timedelta(hours=25):
            _dispatch_interval_reminder(m, MeetingNotification.NotificationType.REMINDER_24H, "24-Hour Reminder", "24 hours")
            sent_count += 1

        # 2. 1-hour reminder (between 50m and 70m)
        elif timedelta(minutes=50) <= time_until_start <= timedelta(minutes=70):
            _dispatch_interval_reminder(m, MeetingNotification.NotificationType.REMINDER_1H, "1-Hour Reminder", "1 hour")
            sent_count += 1

        # 3. 15-minute reminder (between 10m and 20m)
        elif timedelta(minutes=10) <= time_until_start <= timedelta(minutes=20):
            _dispatch_interval_reminder(m, MeetingNotification.NotificationType.REMINDER_15M, "15-Minute Reminder", "15 minutes")
            sent_count += 1

    return sent_count


def _dispatch_interval_reminder(meeting: Meeting, notif_type: str, label: str, time_str: str):
    participants = MeetingParticipant.objects.filter(meeting=meeting).select_related("user")
    users = {p.user for p in participants}
    users.add(meeting.host)
    users.add(meeting.client)

    title = f"{label}: {meeting.title}"
    msg = (
        f"This is a reminder that your scheduled AccrediSure consultation is starting in approximately {time_str} "
        f"at {meeting.start_time.strftime('%I:%M %p UTC')}. Join link: {meeting.zoom_join_url}"
    )

    for user in users:
        # Avoid duplicate reminders of same type for this user & meeting
        if not MeetingNotification.objects.filter(user=user, meeting=meeting, notification_type=notif_type).exists():
            send_notification(user, meeting, notif_type, title, msg)
