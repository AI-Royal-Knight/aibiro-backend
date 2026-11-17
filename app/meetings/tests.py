from datetime import timedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from app.accounts.models import UserAccount
from app.projects.models import Project, ProjectPhase, ProjectTask, BoardTask
from .models import AvailabilitySchedule, Meeting, MeetingParticipant, MeetingHistory


class MeetingFeatureTests(APITestCase):
    def setUp(self):
        self.admin = UserAccount.objects.create_user(
            email="testadmin@accredisure.com",
            password="Password123!",
            role=UserAccount.Role.ADMIN,
            full_name="Operations Lead",
        )
        self.client_user = UserAccount.objects.create_user(
            email="testclient@healthcare.com",
            password="Password123!",
            role=UserAccount.Role.CLIENT,
            full_name="Hospital Director",
        )
        self.staff = UserAccount.objects.create_user(
            email="teststaff@accredisure.com",
            password="Password123!",
            role=UserAccount.Role.STAFF,
            full_name="Compliance Specialist",
            job_title="Compliance Architect",
        )

        self.project = Project.objects.create(
            name="CARF Accreditation Consulting",
            company_name="Horizon Behavioral Health",
            owner=self.client_user,
        )
        self.phase = ProjectPhase.objects.create(
            project=self.project,
            phase_number=1,
            name="Phase 1: Discovery & Policy Architecture",
        )

        self.schedule = AvailabilitySchedule.objects.create(
            owner=self.admin,
            name="Consulting Hours",
            buffer_after_minutes=15,
            min_booking_notice_hours=1,
            min_cancel_notice_hours=2,
            weekly_availability={
                "monday": [{"start": "09:00", "end": "17:00"}],
                "tuesday": [{"start": "09:00", "end": "17:00"}],
                "wednesday": [{"start": "09:00", "end": "17:00"}],
                "thursday": [{"start": "09:00", "end": "17:00"}],
                "friday": [{"start": "09:00", "end": "17:00"}],
                "saturday": [],
                "sunday": [],
            },
        )

    def test_availability_schedule_get_and_patch(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/meetings/availability/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["success"])

        # Patch buffer and durations
        patch_res = self.client.patch("/api/meetings/availability/", {
            "buffer_after_minutes": 20,
            "min_cancel_notice_hours": 6,
        }, format="json")
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data["data"]["buffer_after_minutes"], 20)

    def test_available_slots_calculation(self):
        self.client.force_authenticate(user=self.client_user)
        
        # Pick next Monday
        now = timezone.now()
        days_ahead = (0 - now.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        target_date = (now + timedelta(days=days_ahead)).date()

        res = self.client.get(f"/api/meetings/available-slots/?date={target_date.strftime('%Y-%m-%d')}&duration=30")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["success"])
        self.assertGreater(len(res.data["slots"]), 0)

    def test_client_booking_and_double_booking_lock(self):
        self.client.force_authenticate(user=self.client_user)
        booking_time = timezone.now() + timedelta(days=2, hours=3)

        payload = {
            "start_time": booking_time.isoformat(),
            "duration_minutes": 30,
            "project_id": str(self.project.id),
            "purpose": "CARF Policy Review & Mock Survey Alignment",
            "questions_concerns": "Clarification on surveyor tracer checklists",
            "notes": "Leadership team will be attending",
        }
        res = self.client.post("/api/meetings/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        meeting_data = res.data["data"]
        self.assertTrue(meeting_data["zoom_join_url"].startswith("http"))
        self.assertEqual(meeting_data["project_name"], "CARF Accreditation Consulting")

        # Attempt to book the exact same slot (double booking prevention)
        dup_res = self.client.post("/api/meetings/", payload, format="json")
        self.assertEqual(dup_res.status_code, status.HTTP_409_CONFLICT)

    def test_admin_initiated_meeting_with_staff_invitation(self):
        self.client.force_authenticate(user=self.admin)
        booking_time = timezone.now() + timedelta(days=3, hours=2)

        payload = {
            "client_id": str(self.client_user.id),
            "project_id": str(self.project.id),
            "start_time": booking_time.isoformat(),
            "duration_minutes": 45,
            "purpose": "Executive Project Milestone Review",
            "staff_ids": [str(self.staff.id)],
        }
        res = self.client.post("/api/meetings/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        meeting = Meeting.objects.get(id=res.data["data"]["id"])
        
        # Verify staff was added as participant
        is_staff_participant = MeetingParticipant.objects.filter(meeting=meeting, user=self.staff).exists()
        self.assertTrue(is_staff_participant)

    def test_reschedule_and_cancel_meeting(self):
        self.client.force_authenticate(user=self.client_user)
        booking_time = timezone.now() + timedelta(days=4)

        # 1. Create meeting
        create_res = self.client.post("/api/meetings/", {
            "start_time": booking_time.isoformat(),
            "duration_minutes": 30,
            "purpose": "Documentation Alignment",
        }, format="json")
        meeting_id = create_res.data["data"]["id"]

        # 2. Reschedule
        new_time = timezone.now() + timedelta(days=5)
        reschedule_res = self.client.post(f"/api/meetings/{meeting_id}/reschedule/", {
            "new_start_time": new_time.isoformat(),
            "reason": "Leadership schedule conflict",
        }, format="json")
        self.assertEqual(reschedule_res.status_code, status.HTTP_200_OK)
        self.assertEqual(reschedule_res.data["data"]["status"], "rescheduled")

        # 3. Cancel
        cancel_res = self.client.post(f"/api/meetings/{meeting_id}/cancel/", {
            "reason": "Internal realignment",
        }, format="json")
        self.assertEqual(cancel_res.status_code, status.HTTP_200_OK)
        meeting = Meeting.objects.get(id=meeting_id)
        self.assertEqual(meeting.status, "canceled")

    def test_ai_summary_generation_and_cmr_task_conversion(self):
        self.client.force_authenticate(user=self.admin)
        booking_time = timezone.now() + timedelta(days=1)

        # 1. Create meeting
        create_res = self.client.post("/api/meetings/", {
            "client_id": str(self.client_user.id),
            "project_id": str(self.project.id),
            "start_time": booking_time.isoformat(),
            "duration_minutes": 30,
            "purpose": "Review CARF documentation progress",
        }, format="json")
        meeting_id = create_res.data["data"]["id"]

        # 2. Generate AI Summary & Transcript
        ai_res = self.client.post(f"/api/meetings/{meeting_id}/generate-ai-summary/")
        self.assertEqual(ai_res.status_code, status.HTTP_200_OK)
        summary = ai_res.data["data"]["ai_summary"]
        self.assertIn("meeting_purpose", summary)
        self.assertIn("action_items", summary)
        self.assertGreater(len(summary["action_items"]), 0)

        # 3. Convert action item to CMR Task
        first_action_item = summary["action_items"][0]
        convert_payload = {
            "action_item_id": first_action_item["id"],
            "project_id": str(self.project.id),
            "phase_id": str(self.phase.id),
            "assigned_to_id": str(self.staff.id),
            "title": "Update Client Employee Handbook",
            "due_date": "2026-11-01",
            "priority": "High",
            "responsible_role": "Compliance Architect",
        }
        convert_res = self.client.post(f"/api/meetings/{meeting_id}/convert-action-item/", convert_payload, format="json")
        self.assertEqual(convert_res.status_code, status.HTTP_200_OK)
        self.assertTrue(convert_res.data["success"])

        # Verify task created in ProjectTask
        task = ProjectTask.objects.get(id=convert_res.data["task_id"])
        self.assertEqual(task.title, "Update Client Employee Handbook")
        self.assertEqual(task.assigned_to, self.staff)
        self.assertEqual(task.project, self.project)
        self.assertEqual(task.priority, "High")

        # Verify task created in BoardTask
        board_task = BoardTask.objects.filter(title="Update Client Employee Handbook").first()
        self.assertIsNotNone(board_task)
        self.assertEqual(board_task.assigned_to, self.staff)
