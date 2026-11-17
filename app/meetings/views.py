from datetime import datetime, time, timedelta, timezone as dt_timezone
from django.db import models, transaction
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from app.accounts.models import UserAccount
from app.projects.models import Project, ProjectPhase, ProjectTask, BoardTask
from .ai_service import generate_structured_ai_summary
from .models import (
    AvailabilitySchedule,
    Meeting,
    MeetingParticipant,
    MeetingHistory,
    MeetingNotification,
)
from .reminders import (
    notify_booking_confirmation,
    notify_canceled,
    notify_rescheduled,
    notify_staff_added,
    process_due_reminders,
)
from .serializers import (
    AddStaffSerializer,
    AISummaryUpdateSerializer,
    AvailabilityScheduleSerializer,
    ConvertActionItemToTaskSerializer,
    MeetingBookRequestSerializer,
    MeetingCancelSerializer,
    MeetingDetailSerializer,
    MeetingListSerializer,
    MeetingNotificationSerializer,
    MeetingRescheduleSerializer,
)
from .zoom_service import create_zoom_meeting, delete_zoom_meeting, update_zoom_meeting


def get_default_host():
    """
    Finds an admin or super_admin to act as default host for bookings.
    """
    host = UserAccount.objects.filter(role__in=[UserAccount.Role.ADMIN, UserAccount.Role.SUPER_ADMIN], is_active=True).first()
    if not host:
        host = UserAccount.objects.filter(is_superuser=True).first()
    return host


class AvailabilityScheduleView(APIView):
    """
    Get or update Admin calendar availability configuration.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        schedule = AvailabilitySchedule.objects.filter(is_active=True).first()
        if not schedule:
            host = get_default_host()
            if not host:
                return Response({"error": "No administrative host configured"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            schedule = AvailabilitySchedule.objects.create(
                owner=host,
                name="AccrediSure Consulting Hours",
            )
        serializer = AvailabilityScheduleSerializer(schedule)
        return Response({"success": True, "data": serializer.data})

    def put(self, request: Request) -> Response:
        return self.patch(request)

    def patch(self, request: Request) -> Response:
        user = request.user
        if not (user.is_admin_user or user.is_staff):
            return Response({"detail": "Only Admin/Operations Manager can configure availability."}, status=status.HTTP_403_FORBIDDEN)

        schedule = AvailabilitySchedule.objects.filter(is_active=True).first()
        if not schedule:
            schedule = AvailabilitySchedule.objects.create(owner=user)

        serializer = AvailabilityScheduleSerializer(schedule, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        return Response({"success": True, "message": "Availability updated successfully.", "data": AvailabilityScheduleSerializer(updated).data})


class AvailableSlotsView(APIView):
    """
    Calculates bookable time slots for a given date or date range based on
    the host's availability schedule, existing bookings, buffer periods, and notice rules.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        date_str = request.query_params.get("date")
        duration_min = int(request.query_params.get("duration", 30))
        
        schedule = AvailabilitySchedule.objects.filter(is_active=True).first()
        if not schedule:
            host = get_default_host()
            schedule = AvailabilitySchedule.objects.create(owner=host)

        if not date_str:
            target_date = timezone.now().date()
        else:
            try:
                target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                return Response({"error": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Check blackout dates
        blackout_dates = [b.get("date") if isinstance(b, dict) else b for b in (schedule.blackout_dates or [])]
        if target_date.strftime("%Y-%m-%d") in blackout_dates:
            return Response({"success": True, "date": target_date.strftime("%Y-%m-%d"), "slots": [], "message": "Date is marked unavailable (blackout date)."})

        # 2. Check weekly day of week
        weekday_name = target_date.strftime("%A").lower()
        windows = schedule.weekly_availability.get(weekday_name, [])
        if not windows:
            return Response({"success": True, "date": target_date.strftime("%Y-%m-%d"), "slots": [], "message": f"No availability configured for {weekday_name.capitalize()}s."})

        # 3. Retrieve host's existing active meetings on that date
        start_of_day = datetime.combine(target_date, time.min).replace(tzinfo=dt_timezone.utc)
        end_of_day = datetime.combine(target_date, time.max).replace(tzinfo=dt_timezone.utc)
        
        booked_meetings = Meeting.objects.filter(
            host=schedule.owner,
            status__in=[Meeting.MeetingStatus.SCHEDULED, Meeting.MeetingStatus.RESCHEDULED],
            start_time__lte=end_of_day,
            end_time__gte=start_of_day,
        )

        buffer_after = timedelta(minutes=schedule.buffer_after_minutes)
        min_notice_time = timezone.now() + timedelta(hours=schedule.min_booking_notice_hours)

        available_slots = []

        for window in windows:
            try:
                w_start_hour, w_start_min = map(int, window["start"].split(":"))
                w_end_hour, w_end_min = map(int, window["end"].split(":"))
            except (ValueError, KeyError):
                continue

            window_start = datetime.combine(target_date, time(w_start_hour, w_start_min)).replace(tzinfo=dt_timezone.utc)
            window_end = datetime.combine(target_date, time(w_end_hour, w_end_min)).replace(tzinfo=dt_timezone.utc)

            current_cursor = window_start
            slot_step = timedelta(minutes=duration_min)

            while current_cursor + slot_step <= window_end:
                slot_start = current_cursor
                slot_end = current_cursor + slot_step

                # Must satisfy minimum notice rule
                if slot_start >= min_notice_time:
                    # Check collision with existing meetings (+ buffers)
                    has_collision = False
                    for m in booked_meetings:
                        # Meeting busy window includes buffer after
                        m_busy_start = m.start_time
                        m_busy_end = m.end_time + buffer_after
                        
                        # Collision condition: (slot_start < m_busy_end) and (slot_end + buffer_after > m_busy_start)
                        if (slot_start < m_busy_end) and ((slot_end + buffer_after) > m_busy_start):
                            has_collision = True
                            break

                    if not has_collision:
                        available_slots.append({
                            "start_time": slot_start.isoformat(),
                            "end_time": slot_end.isoformat(),
                            "formatted": f"{slot_start.strftime('%I:%M %p')} - {slot_end.strftime('%I:%M %p')} UTC",
                            "duration_minutes": duration_min,
                        })

                # Advance cursor by slot duration + buffer
                current_cursor += slot_step + buffer_after

        return Response({
            "success": True,
            "date": target_date.strftime("%Y-%m-%d"),
            "schedule_owner": schedule.owner.full_name or schedule.owner.email,
            "buffer_after_minutes": schedule.buffer_after_minutes,
            "slots": available_slots,
        })


class MeetingListCreateView(APIView):
    """
    List meetings for the current user or book/schedule a new meeting.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = request.user
        queryset = Meeting.objects.all().select_related("host", "client", "project", "phase").prefetch_related("participants__user")

        if user.is_admin_user:
            pass  # Admin sees all
        elif user.role == UserAccount.Role.STAFF:
            # Staff see meetings they are invited to or host
            queryset = queryset.filter(models.Q(participants__user=user) | models.Q(host=user)).distinct()
        else:
            # Client sees their own meetings
            queryset = queryset.filter(client=user)

        # Filters
        status_filter = request.query_params.get("status")
        now = timezone.now()
        if status_filter == "upcoming":
            queryset = queryset.filter(status__in=[Meeting.MeetingStatus.SCHEDULED, Meeting.MeetingStatus.RESCHEDULED], end_time__gte=now)
        elif status_filter == "past":
            queryset = queryset.filter(models.Q(status=Meeting.MeetingStatus.COMPLETED) | models.Q(end_time__lt=now))
        elif status_filter == "canceled":
            queryset = queryset.filter(status=Meeting.MeetingStatus.CANCELED)

        project_id = request.query_params.get("project_id")
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        client_id = request.query_params.get("client_id")
        if client_id and user.is_admin_user:
            queryset = queryset.filter(client_id=client_id)

        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                models.Q(title__icontains=search)
                | models.Q(purpose__icontains=search)
                | models.Q(project__name__icontains=search)
                | models.Q(client__email__icontains=search)
                | models.Q(client__full_name__icontains=search)
            )

        queryset = queryset.order_by("start_time")
        serializer = MeetingListSerializer(queryset, many=True)
        return Response({"success": True, "count": queryset.count(), "data": serializer.data})

    def post(self, request: Request) -> Response:
        """
        Schedule / Book a meeting.
        """
        serializer = MeetingBookRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = request.user
        start_time = data["start_time"]
        duration = data["duration_minutes"]
        end_time = start_time + timedelta(minutes=duration)

        # Resolve host and client
        schedule = AvailabilitySchedule.objects.filter(is_active=True).first()
        host = schedule.owner if schedule else get_default_host()

        if user.is_admin_user:
            # Admin initiated
            client_id = data.get("client_id")
            if not client_id:
                return Response({"error": "client_id is required when Admin initiates a meeting."}, status=status.HTTP_400_BAD_REQUEST)
            client = UserAccount.objects.filter(id=client_id).first()
            if not client:
                return Response({"error": "Selected client was not found."}, status=status.HTTP_404_NOT_FOUND)
            initiated_by = Meeting.Initiator.ADMIN
        else:
            # Client initiated
            client = user
            initiated_by = Meeting.Initiator.CLIENT

        # Atomic double-booking prevention lock
        with transaction.atomic():
            buffer_after = timedelta(minutes=schedule.buffer_after_minutes if schedule else 15)
            
            # Check collisions with host
            collision = Meeting.objects.select_for_update().filter(
                host=host,
                status__in=[Meeting.MeetingStatus.SCHEDULED, Meeting.MeetingStatus.RESCHEDULED],
                start_time__lt=end_time + buffer_after,
                end_time__gt=start_time - buffer_after,
            ).exists()

            if collision:
                return Response(
                    {"error": "This time slot is no longer available. Please select another slot."},
                    status=status.HTTP_409_CONFLICT,
                )

            # Project association
            project = None
            if data.get("project_id"):
                project = Project.objects.filter(id=data["project_id"]).first()

            phase = None
            if data.get("phase_id"):
                phase = ProjectPhase.objects.filter(id=data["phase_id"]).first()

            # Automatic Zoom Meeting creation
            meeting_title = data.get("title") or (f"Consultation with {client.full_name or client.company_name or client.email}")
            zoom_data = create_zoom_meeting(
                topic=meeting_title,
                start_time=start_time,
                duration_minutes=duration,
                agenda=data["purpose"],
            )

            # Create Meeting instance
            meeting = Meeting.objects.create(
                title=meeting_title,
                host=host,
                client=client,
                project=project,
                phase=phase,
                start_time=start_time,
                end_time=end_time,
                duration_minutes=duration,
                timezone="America/New_York",
                status=Meeting.MeetingStatus.SCHEDULED,
                initiated_by=initiated_by,
                purpose=data["purpose"],
                questions_concerns=data.get("questions_concerns", ""),
                notes=data.get("notes", ""),
                zoom_meeting_id=zoom_data.get("meeting_id", ""),
                zoom_join_url=zoom_data.get("join_url", ""),
                zoom_start_url=zoom_data.get("start_url", ""),
                zoom_passcode=zoom_data.get("passcode", ""),
            )

            # Create default participants
            MeetingParticipant.objects.create(
                meeting=meeting,
                user=host,
                role=MeetingParticipant.ParticipantRole.HOST,
                is_organizer=True,
            )
            MeetingParticipant.objects.create(
                meeting=meeting,
                user=client,
                role=MeetingParticipant.ParticipantRole.CLIENT,
            )

            # Add optional staff members
            staff_ids = data.get("staff_ids", [])
            for s_id in staff_ids:
                staff_user = UserAccount.objects.filter(id=s_id).first()
                if staff_user and staff_user != host and staff_user != client:
                    MeetingParticipant.objects.create(
                        meeting=meeting,
                        user=staff_user,
                        role=MeetingParticipant.ParticipantRole.STAFF,
                        added_by=user,
                    )
                    notify_staff_added(meeting, staff_user, user)

            # Log history
            MeetingHistory.objects.create(
                meeting=meeting,
                actor=user,
                action=MeetingHistory.Action.SCHEDULED,
                new_start_time=start_time,
                reason="Meeting booked and confirmed.",
                details={"duration": duration, "initiated_by": initiated_by},
            )

            # Send immediate booking confirmations
            notify_booking_confirmation(meeting)

        return Response(
            {
                "success": True,
                "message": "Meeting successfully scheduled.",
                "data": MeetingDetailSerializer(meeting).data,
            },
            status=status.HTTP_201_CREATED,
        )


class MeetingDetailView(APIView):
    """
    Retrieve single meeting details.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, pk: str) -> Response:
        meeting = Meeting.objects.filter(pk=pk).select_related("host", "client", "project", "phase").prefetch_related("participants__user", "history__actor").first()
        if not meeting:
            return Response({"error": "Meeting not found."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        is_participant = meeting.participants.filter(user=user).exists()
        if not (user.is_admin_user or meeting.host == user or meeting.client == user or is_participant):
            return Response({"detail": "You do not have access to this meeting."}, status=status.HTTP_403_FORBIDDEN)

        serializer = MeetingDetailSerializer(meeting)
        return Response({"success": True, "data": serializer.data})


class MeetingRescheduleView(APIView):
    """
    Reschedule an existing meeting to a new available time slot.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, pk: str) -> Response:
        meeting = Meeting.objects.filter(pk=pk).first()
        if not meeting:
            return Response({"error": "Meeting not found."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        if not (user.is_admin_user or meeting.client == user or meeting.host == user):
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        serializer = MeetingRescheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Minimum notice check for clients
        schedule = AvailabilitySchedule.objects.filter(is_active=True).first()
        min_notice_hours = schedule.min_cancel_notice_hours if schedule else 4
        if not user.is_admin_user:
            notice_threshold = timezone.now() + timedelta(hours=min_notice_hours)
            if meeting.start_time <= notice_threshold:
                return Response(
                    {"error": f"Meetings cannot be rescheduled within {min_notice_hours} hours of start time. Please contact your Operations Manager."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        new_start = data["new_start_time"]
        duration = data.get("duration_minutes") or meeting.duration_minutes
        new_end = new_start + timedelta(minutes=duration)

        with transaction.atomic():
            old_start = meeting.start_time
            meeting.start_time = new_start
            meeting.end_time = new_end
            meeting.duration_minutes = duration
            meeting.status = Meeting.MeetingStatus.RESCHEDULED
            meeting.save(update_fields=["start_time", "end_time", "duration_minutes", "status", "updated_at"])

            # Update Zoom meeting
            update_zoom_meeting(meeting.zoom_meeting_id, meeting.title, new_start, duration)

            # Audit history
            MeetingHistory.objects.create(
                meeting=meeting,
                actor=user,
                action=MeetingHistory.Action.RESCHEDULED,
                previous_start_time=old_start,
                new_start_time=new_start,
                reason=data.get("reason", "Rescheduled by participant"),
            )

            # Notify participants
            notify_rescheduled(meeting, user, data.get("reason", ""))

        return Response({"success": True, "message": "Meeting successfully rescheduled.", "data": MeetingDetailSerializer(meeting).data})


class MeetingCancelView(APIView):
    """
    Cancel an existing meeting with an audit log reason.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, pk: str) -> Response:
        meeting = Meeting.objects.filter(pk=pk).first()
        if not meeting:
            return Response({"error": "Meeting not found."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        if not (user.is_admin_user or meeting.client == user or meeting.host == user):
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        serializer = MeetingCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get("reason", "")

        # Minimum notice check for clients
        schedule = AvailabilitySchedule.objects.filter(is_active=True).first()
        min_notice_hours = schedule.min_cancel_notice_hours if schedule else 4
        if not user.is_admin_user:
            notice_threshold = timezone.now() + timedelta(hours=min_notice_hours)
            if meeting.start_time <= notice_threshold:
                return Response(
                    {"error": f"Meetings cannot be canceled within {min_notice_hours} hours of start time. Please contact your Operations Manager."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        meeting.status = Meeting.MeetingStatus.CANCELED
        meeting.save(update_fields=["status", "updated_at"])

        # Cancel on Zoom
        delete_zoom_meeting(meeting.zoom_meeting_id)

        # Log history
        MeetingHistory.objects.create(
            meeting=meeting,
            actor=user,
            action=MeetingHistory.Action.CANCELED,
            reason=reason or "Canceled by user",
        )

        # Notify participants
        notify_canceled(meeting, user, reason)

        return Response({"success": True, "message": "Meeting canceled successfully."})


class MeetingAddStaffView(APIView):
    """
    Admin/Operations Manager adds an AccrediSure staff member to an existing meeting.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, pk: str) -> Response:
        meeting = Meeting.objects.filter(pk=pk).first()
        if not meeting:
            return Response({"error": "Meeting not found."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        if not (user.is_admin_user or meeting.host == user):
            return Response({"detail": "Only Admin/Operations Manager can add staff to client meetings."}, status=status.HTTP_403_FORBIDDEN)

        serializer = AddStaffSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        staff_ids = serializer.validated_data["staff_ids"]

        added_count = 0
        for s_id in staff_ids:
            staff = UserAccount.objects.filter(id=s_id).first()
            if staff and not MeetingParticipant.objects.filter(meeting=meeting, user=staff).exists():
                MeetingParticipant.objects.create(
                    meeting=meeting,
                    user=staff,
                    role=MeetingParticipant.ParticipantRole.STAFF,
                    added_by=user,
                )
                MeetingHistory.objects.create(
                    meeting=meeting,
                    actor=user,
                    action=MeetingHistory.Action.STAFF_ADDED,
                    reason=f"Added staff member {staff.full_name or staff.email}",
                )
                notify_staff_added(meeting, staff, user)
                added_count += 1

        return Response({
            "success": True,
            "message": f"Successfully added {added_count} staff member(s).",
            "data": MeetingDetailSerializer(meeting).data,
        })


class MeetingRemoveStaffView(APIView):
    """
    Admin/Operations Manager removes an AccrediSure staff member from an existing meeting.
    """
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request: Request, pk: str, staff_id: str) -> Response:
        meeting = Meeting.objects.filter(pk=pk).first()
        if not meeting:
            return Response({"error": "Meeting not found."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        if not (user.is_admin_user or meeting.host == user):
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        participant = MeetingParticipant.objects.filter(meeting=meeting, user_id=staff_id).first()
        if participant:
            staff_name = participant.user.full_name or participant.user.email
            participant.delete()
            MeetingHistory.objects.create(
                meeting=meeting,
                actor=user,
                action=MeetingHistory.Action.STAFF_REMOVED,
                reason=f"Removed staff member {staff_name}",
            )

        return Response({"success": True, "message": "Staff member removed from meeting."})


class MeetingAISummaryGenerateView(APIView):
    """
    Generates AI transcription and structured meeting summary with action items.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, pk: str) -> Response:
        meeting = Meeting.objects.filter(pk=pk).first()
        if not meeting:
            return Response({"error": "Meeting not found."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        if not (user.is_admin_user or meeting.host == user):
            return Response({"detail": "Only Admin/Operations Manager can generate AI summaries."}, status=status.HTTP_403_FORBIDDEN)

        custom_transcript = request.data.get("transcript_text", "")
        result = generate_structured_ai_summary(meeting, custom_transcript)

        meeting.transcript_text = result["transcript_text"]
        meeting.ai_summary = result["ai_summary"]
        meeting.ai_summary_status = Meeting.AISummaryStatus.GENERATED
        meeting.zoom_recording_url = result["zoom_recording_url"]
        meeting.status = Meeting.MeetingStatus.COMPLETED
        meeting.save(update_fields=["transcript_text", "ai_summary", "ai_summary_status", "zoom_recording_url", "status", "updated_at"])

        MeetingHistory.objects.create(
            meeting=meeting,
            actor=user,
            action=MeetingHistory.Action.SUMMARY_UPDATED,
            reason="AI summary and transcript generated.",
        )

        return Response({
            "success": True,
            "message": "AI transcription and summary generated successfully.",
            "data": MeetingDetailSerializer(meeting).data,
        })


class MeetingAISummaryUpdateView(APIView):
    """
    Admin reviews and edits the AI-generated summary before finalizing into project record.
    """
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request: Request, pk: str) -> Response:
        meeting = Meeting.objects.filter(pk=pk).first()
        if not meeting:
            return Response({"error": "Meeting not found."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        if not (user.is_admin_user or meeting.host == user):
            return Response({"detail": "Only Admin/Operations Manager can edit AI summaries."}, status=status.HTTP_403_FORBIDDEN)

        serializer = AISummaryUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        meeting.ai_summary = data["ai_summary"]
        if "admin_notes" in data:
            meeting.admin_notes = data["admin_notes"]
        if "ai_summary_status" in data:
            meeting.ai_summary_status = data["ai_summary_status"]

        meeting.save(update_fields=["ai_summary", "admin_notes", "ai_summary_status", "updated_at"])

        MeetingHistory.objects.create(
            meeting=meeting,
            actor=user,
            action=MeetingHistory.Action.SUMMARY_UPDATED,
            reason="Admin reviewed and updated meeting summary.",
        )

        return Response({
            "success": True,
            "message": "Meeting summary saved successfully.",
            "data": MeetingDetailSerializer(meeting).data,
        })


class MeetingConvertActionItemView(APIView):
    """
    Directly converts an AI-identified action item into a real CMR Project Task & Board Task!
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, pk: str) -> Response:
        meeting = Meeting.objects.filter(pk=pk).select_related("project").first()
        if not meeting:
            return Response({"error": "Meeting not found."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        if not (user.is_admin_user or meeting.host == user):
            return Response({"detail": "Only Admin/Operations Manager can convert action items to CMR tasks."}, status=status.HTTP_403_FORBIDDEN)

        serializer = ConvertActionItemToTaskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        action_item_id = data["action_item_id"]
        project = Project.objects.filter(id=data["project_id"]).first()
        if not project:
            return Response({"error": "Target CMR project not found."}, status=status.HTTP_404_NOT_FOUND)

        # Locate action item in meeting.ai_summary
        summary = meeting.ai_summary or {}
        action_items = summary.get("action_items", [])
        matched_item = None
        for item in action_items:
            if item.get("id") == action_item_id:
                matched_item = item
                break

        if not matched_item:
            return Response({"error": "Action item ID not found in meeting summary."}, status=status.HTTP_404_NOT_FOUND)

        # Pick or create phase
        phase = None
        if data.get("phase_id"):
            phase = ProjectPhase.objects.filter(id=data["phase_id"]).first()
        if not phase:
            phase = project.phases.first()
        if not phase:
            phase = ProjectPhase.objects.create(
                project=project,
                name="Phase 1: Implementation & Follow-Up",
                phase_number=1,
            )

        # Assigned staff
        assigned_to = None
        if data.get("assigned_to_id"):
            assigned_to = UserAccount.objects.filter(id=data["assigned_to_id"]).first()

        task_title = data.get("title") or matched_item.get("title") or "Meeting Action Item"
        task_desc = matched_item.get("description", "")
        due_date = data.get("due_date")

        # 1. Create ProjectTask under CMR workflow
        project_task = ProjectTask.objects.create(
            project=project,
            phase=phase,
            title=task_title,
            responsible_role=data.get("responsible_role", "Compliance Architect"),
            assigned_to=assigned_to,
            due_date=due_date,
            status=ProjectTask.TaskStatus.TODO,
            priority=data.get("priority", "Medium"),
            submission_notes=f"Converted from meeting '{meeting.title}' action item.\nContext: {task_desc}",
            is_custom=True,
        )

        # 2. Create BoardTask on global task board
        BoardTask.objects.create(
            title=task_title,
            description=f"CMR Project: {project.name}\nPhase: {phase.name}\nMeeting: {meeting.title}\n{task_desc}",
            client_name=project.company_name,
            assigned_to=assigned_to,
            due_date=due_date,
            status="To Do",
            priority=data.get("priority", "Medium"),
        )

        # 3. Update action item in meeting summary
        matched_item["is_converted_to_task"] = True
        matched_item["converted_task_id"] = str(project_task.id)
        meeting.ai_summary = summary
        meeting.save(update_fields=["ai_summary", "updated_at"])

        # 4. History log
        MeetingHistory.objects.create(
            meeting=meeting,
            actor=user,
            action=MeetingHistory.Action.TASK_CONVERTED,
            reason=f"Converted action item '{task_title}' to CMR Task on project '{project.name}'",
            details={"task_id": str(project_task.id), "assigned_to": assigned_to.email if assigned_to else None},
        )

        return Response({
            "success": True,
            "message": f"Action item converted to CMR task on project '{project.name}'.",
            "task_id": str(project_task.id),
            "updated_summary": summary,
        })


class MeetingNotificationListView(generics.ListAPIView):
    """
    List user's meeting notifications.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MeetingNotificationSerializer

    def get_queryset(self):
        return MeetingNotification.objects.filter(user=self.request.user).order_by("-created_at")[:50]


class MeetingNotificationMarkReadView(APIView):
    """
    Mark notification as read.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, pk: str) -> Response:
        notif = MeetingNotification.objects.filter(pk=pk, user=request.user).first()
        if notif:
            notif.is_read = True
            notif.save(update_fields=["is_read"])
        return Response({"success": True})


class TriggerDueRemindersView(APIView):
    """
    Scans upcoming meetings and triggers 24h, 1h, and 15m reminders.
    Can be called by cron or admin trigger.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request) -> Response:
        if not request.user.is_admin_user:
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        count = process_due_reminders()
        return Response({"success": True, "dispatched_reminders": count})
