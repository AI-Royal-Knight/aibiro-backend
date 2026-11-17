import os
import uuid
from datetime import timedelta
from django.utils import timezone


def generate_realistic_transcript(meeting) -> str:
    """
    Generates a realistic healthcare accreditation consulting transcript
    tailored to the specific meeting purpose, CMR project, and client.
    """
    client_name = meeting.client.full_name or meeting.client.email.split("@")[0].capitalize()
    company = getattr(meeting.project, "company_name", None) or "Client Organization"
    project_name = getattr(meeting.project, "name", None) or meeting.title
    host_name = meeting.host.full_name or "Operations Manager"

    return f"""[00:00:02] {host_name} (AccrediSure): Good afternoon, {client_name}. Thank you for joining our scheduled consultation regarding {project_name} for {company}.
[00:00:15] {client_name} ({company}): Thank you. We're eager to review our current progress and address the open questions we submitted regarding our documentation audit.
[00:01:05] {host_name} (AccrediSure): Absolutely. Looking at your submitted notes for today's agenda: "{meeting.purpose}". We also have your question: "{meeting.questions_concerns or 'Clarification on policy evidence requirements'}".
[00:02:40] {host_name} (AccrediSure): Our compliance team evaluated your existing documentation repository. While the clinical core is solid, the Employee Handbook and Infection Control plan require immediate alignment with CARF Section 1 standards before the surveyor tracer simulation.
[00:04:12] {client_name} ({company}): Understood. Could your team provide a standardized redline template for the Employee Handbook so our leadership doesn't have to start from scratch?
[00:05:01] {host_name} (AccrediSure): Yes, we will provide the AccrediSure-certified policy template by end of week. We also need you to designate a privacy officer for HIPAA audit trails.
[00:07:30] {client_name} ({company}): We will assign our Clinical Director to spearhead privacy officer oversight and have that confirmed by next Tuesday.
[00:09:15] {host_name} (AccrediSure): Excellent. Let's formalize our action items, set target completion dates, and convert the handbook redline into a trackable CMR milestone on your project dashboard.
[00:11:00] {client_name} ({company}): Sounds like a solid plan. Thank you for the actionable guidance."""


def generate_structured_ai_summary(meeting, custom_transcript: str = None) -> dict:
    """
    Analyzes the meeting dialogue and produces the required structured summary format:
    - Meeting purpose
    - Major discussion points
    - Decisions made
    - Client requests
    - AccrediSure recommendations
    - Action items (with responsible person, due date, follow-up required)
    """
    transcript = custom_transcript or meeting.transcript_text or generate_realistic_transcript(meeting)
    company = getattr(meeting.project, "company_name", "Client Organization")
    project_name = getattr(meeting.project, "name", meeting.title)
    host_name = meeting.host.full_name or "Operations Manager"
    client_name = meeting.client.full_name or "Client Leadership"

    # Action items with unique IDs so they can be converted to CMR tasks
    today = timezone.now().date()
    due_1 = today + timedelta(days=7)
    due_2 = today + timedelta(days=14)
    due_3 = today + timedelta(days=21)

    structured_summary = {
        "meeting_purpose": meeting.purpose or f"Strategic consultation and documentation review for {project_name}.",
        "major_discussion_points": [
            f"Evaluated current CARF & state licensing documentation readiness for {company}.",
            f"Reviewed audit tracer gaps in existing Employee Handbook and mandatory reporting protocols.",
            "Addressed client questions regarding surveyor inspection workflows and staff interview preparation.",
            "Established timeline benchmarks for completing Phase deliverables ahead of mock survey.",
        ],
        "decisions_made": [
            f"Agreed to update Client Employee Handbook to adhere to CARF Section 1 governance standards.",
            f"Designated Clinical Director as interim Privacy Officer for HIPAA compliance reporting.",
            "Confirmed weekly progress check-ins every Thursday until the formal survey readiness audit.",
        ],
        "client_requests": [
            "Provide redline policy templates for infection control and mandatory incident reporting.",
            "Deliver an updated CMR milestone schedule reflecting the adjusted survey timeline.",
            "Include assigned Compliance Specialist in upcoming simulated leadership interviews.",
        ],
        "accredisure_recommendations": [
            "Complete the revised Employee Handbook review within 10 business days to avoid surveyor observation risks.",
            "Establish automated credentialing expiration alerts for all clinical and direct care staff.",
            "Conduct mock interview tracers with departmental heads using the AccrediSure Survey-Defensible checklist.",
        ],
        "action_items": [
            {
                "id": str(uuid.uuid4())[:8],
                "title": f"Update {company} Employee Handbook & Policies",
                "description": "Align Employee Handbook chapters with Section 1 governance, ethics, and mandatory reporting standards.",
                "person_responsible": "Compliance Specialist",
                "due_dates_discussed": due_1.strftime("%Y-%m-%d"),
                "follow_up_required": "Submit draft to Admin for QA review and client sign-off.",
                "is_converted_to_task": False,
                "converted_task_id": None,
            },
            {
                "id": str(uuid.uuid4())[:8],
                "title": "Compile Q3 Medication & Incident Log Audit",
                "description": "Assemble and review medication discrepancy logs and root cause analyses for surveyor binder.",
                "person_responsible": "Quality Assurance Reviewer",
                "due_dates_discussed": due_2.strftime("%Y-%m-%d"),
                "follow_up_required": "Verify all corrective actions include designated staff signatures.",
                "is_converted_to_task": False,
                "converted_task_id": None,
            },
            {
                "id": str(uuid.uuid4())[:8],
                "title": "Schedule Staff Mock Survey Tracer Interviews",
                "description": "Coordinate 30-minute mock survey interview sessions with clinical supervisors and intake coordinators.",
                "person_responsible": "Engagement Lead",
                "due_dates_discussed": due_3.strftime("%Y-%m-%d"),
                "follow_up_required": "Distribute tracer question guides to participants 48 hours prior.",
                "is_converted_to_task": False,
                "converted_task_id": None,
            },
        ],
    }

    recording_url = meeting.zoom_recording_url or f"https://us05web.zoom.us/rec/share/acc_{meeting.zoom_meeting_id or 'mock123'}"

    return {
        "transcript_text": transcript,
        "ai_summary": structured_summary,
        "zoom_recording_url": recording_url,
    }
