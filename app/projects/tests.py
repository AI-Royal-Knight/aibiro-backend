import io
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from app.accounts.models import UserAccount
from app.accounts.views import get_tokens_for_user
from app.projects.models import Project, Document


class ProjectCreationAndCRUDTests(TestCase):
    """
    Tests covering:
    - Project creation requiring name, company_name, and status.
    - Full & partial field updates.
    - Owner isolation between clients.
    """

    def setUp(self):
        self.client_user = UserAccount.objects.create_user(
            email="client1@example.com",
            password="SecurePassword123!",
            role=UserAccount.Role.CLIENT,
        )
        self.client_token = get_tokens_for_user(self.client_user)["access"]
        self.auth_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.client_token}"}

        self.other_client = UserAccount.objects.create_user(
            email="client2@example.com",
            password="SecurePassword123!",
            role=UserAccount.Role.CLIENT,
        )
        self.other_token = get_tokens_for_user(self.other_client)["access"]
        self.other_auth_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.other_token}"}

        self.admin_user = UserAccount.objects.create_user(
            email="admin@example.com",
            password="SecurePassword123!",
            role=UserAccount.Role.ADMIN,
        )
        self.admin_token = get_tokens_for_user(self.admin_user)["access"]
        self.admin_auth_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"}

    def test_create_project_success_with_required_fields(self):
        """Test creating a project with name, company_name, and status."""
        payload = {
            "name": "CARF Accreditation Survey",
            "company_name": "Horizon Behavioral",
            "status": "active",
            "description": "Comprehensive accreditation readiness review.",
            "compliance_score": 94,
            "days_to_survey": 42,
        }
        resp = self.client.post(
            "/api/projects/",
            data=payload,
            **self.auth_headers,
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertTrue(data["success"])
        project_data = data["data"]
        self.assertEqual(project_data["name"], "CARF Accreditation Survey")
        self.assertEqual(project_data["company_name"], "Horizon Behavioral")
        self.assertEqual(project_data["status"], "active")
        self.assertEqual(project_data["status_display"], "Active")
        self.assertEqual(project_data["compliance_score"], 94)
        self.assertEqual(project_data["days_to_survey"], 42)
        self.assertEqual(project_data["owner_email"], "client1@example.com")

        # Verify DB entry
        project = Project.objects.get(pk=project_data["id"])
        self.assertEqual(project.owner, self.client_user)

    def test_create_project_missing_name_fails(self):
        """Test that missing project name triggers validation error."""
        resp = self.client.post(
            "/api/projects/",
            data={"company_name": "Horizon Behavioral", "status": "active"},
            **self.auth_headers,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("name", resp.json())

    def test_create_project_missing_company_name_fails(self):
        """Test that missing company name triggers validation error."""
        resp = self.client.post(
            "/api/projects/",
            data={"name": "CARF Survey", "status": "active"},
            **self.auth_headers,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("company_name", resp.json())

    def test_create_project_missing_status_fails(self):
        """Test that missing status triggers validation error."""
        resp = self.client.post(
            "/api/projects/",
            data={"name": "CARF Survey", "company_name": "Horizon Behavioral"},
            **self.auth_headers,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("status", resp.json())

    def test_update_all_fields_patch_and_put(self):
        """Test full and partial updates of all project fields."""
        project = Project.objects.create(
            owner=self.client_user,
            name="Initial Name",
            company_name="Initial Company",
            status=Project.ProjectStatus.ACTIVE,
            compliance_score=50,
            days_to_survey=60,
        )

        # PATCH update
        patch_payload = {
            "name": "Updated Name",
            "company_name": "Updated Organization",
            "status": "in_progress",
            "description": "Updated scope and goals.",
            "compliance_score": 90,
            "days_to_survey": 30,
        }
        resp = self.client.patch(
            f"/api/projects/{project.id}/",
            data=patch_payload,
            content_type="application/json",
            **self.auth_headers,
        )
        self.assertEqual(resp.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.name, "Updated Name")
        self.assertEqual(project.company_name, "Updated Organization")
        self.assertEqual(project.status, "in_progress")
        self.assertEqual(project.description, "Updated scope and goals.")
        self.assertEqual(project.compliance_score, 90)
        self.assertEqual(project.days_to_survey, 30)

        # PUT full update
        put_payload = {
            "name": "Fully Updated Name",
            "company_name": "Fully Updated Organization",
            "status": "completed",
            "description": "Completed accreditation.",
            "compliance_score": 100,
            "days_to_survey": 0,
        }
        resp = self.client.put(
            f"/api/projects/{project.id}/",
            data=put_payload,
            content_type="application/json",
            **self.auth_headers,
        )
        self.assertEqual(resp.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.name, "Fully Updated Name")
        self.assertEqual(project.status, "completed")
        self.assertEqual(project.compliance_score, 100)

    def test_other_client_cannot_access_or_update_project(self):
        """Test project isolation: client B cannot update or delete client A's project."""
        project = Project.objects.create(
            owner=self.client_user,
            name="Client A Project",
            company_name="Org A",
            status=Project.ProjectStatus.ACTIVE,
        )

        # Other client tries GET
        resp = self.client.get(
            f"/api/projects/{project.id}/",
            **self.other_auth_headers,
        )
        self.assertEqual(resp.status_code, 403)

        # Other client tries PATCH
        resp = self.client.patch(
            f"/api/projects/{project.id}/",
            data={"name": "Hacked"},
            content_type="application/json",
            **self.other_auth_headers,
        )
        self.assertEqual(resp.status_code, 403)

        # Other client tries DELETE
        resp = self.client.delete(
            f"/api/projects/{project.id}/",
            **self.other_auth_headers,
        )
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_view_and_update_any_project(self):
        """Admins can view and update any client's project."""
        project = Project.objects.create(
            owner=self.client_user,
            name="Client Project",
            company_name="Org A",
            status=Project.ProjectStatus.ACTIVE,
        )
        resp = self.client.get(
            f"/api/projects/{project.id}/",
            **self.admin_auth_headers,
        )
        self.assertEqual(resp.status_code, 200)

        resp = self.client.patch(
            f"/api/projects/{project.id}/",
            data={"status": "archived"},
            content_type="application/json",
            **self.admin_auth_headers,
        )
        self.assertEqual(resp.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.status, "archived")


class DocumentUploadTests(TestCase):
    """
    Tests covering:
    - Uploading any file format (PDF, DOCX, XLSX, TXT, images, archives).
    - Preserving file metadata, original filename, and size.
    - Listing and deleting files.
    - File review status updates.
    """

    def setUp(self):
        self.client_user = UserAccount.objects.create_user(
            email="client@example.com",
            password="SecurePassword123!",
            role=UserAccount.Role.CLIENT,
        )
        self.client_token = get_tokens_for_user(self.client_user)["access"]
        self.auth_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.client_token}"}

        self.project = Project.objects.create(
            owner=self.client_user,
            name="CARF Project",
            company_name="Horizon Behavioral",
            status=Project.ProjectStatus.ACTIVE,
        )

    def test_upload_multiple_file_types_under_project(self):
        """Verify upload of PDF, DOCX, XLSX, and generic file types."""
        files_to_upload = [
            ("Clinical_Policy_v2.pdf", b"%PDF-1.4 dummy pdf content", "application/pdf"),
            ("Governance_Framework.docx", b"PK\x03\x04 dummy docx content", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            ("Staff_Training_Log_2025.xlsx", b"PK\x03\x04 dummy xlsx content", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("survey_notes.txt", b"Plain text survey notes", "text/plain"),
        ]

        for filename, content, mime_type in files_to_upload:
            uploaded_file = SimpleUploadedFile(
                name=filename,
                content=content,
                content_type=mime_type,
            )
            resp = self.client.post(
                f"/api/projects/{self.project.id}/files/",
                data={"file": uploaded_file, "status": "pending_review"},
                format="multipart",
                **self.auth_headers,
            )
            self.assertEqual(resp.status_code, 201)
            data = resp.json()["data"]
            self.assertEqual(data["original_name"], filename)
            self.assertEqual(data["file_size"], len(content))
            self.assertEqual(data["status"], "pending_review")
            self.assertEqual(data["status_display"], "Pending AI Review")
            self.assertIn("file_url", data)

        self.assertEqual(self.project.files.count(), 4)

    def test_list_documents(self):
        """Test retrieving all files under a project."""
        Document.objects.create(
            project=self.project,
            uploaded_by=self.client_user,
            file=SimpleUploadedFile("doc1.pdf", b"pdf content"),
            original_name="doc1.pdf",
            file_size=11,
            status=Document.FileStatus.REVIEWED,
        )
        Document.objects.create(
            project=self.project,
            uploaded_by=self.client_user,
            file=SimpleUploadedFile("doc2.xlsx", b"xlsx content"),
            original_name="doc2.xlsx",
            file_size=12,
            status=Document.FileStatus.FLAGGED,
        )

        resp = self.client.get(
            f"/api/projects/{self.project.id}/files/",
            **self.auth_headers,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 2)
        statuses = [f["status"] for f in data["data"]]
        self.assertIn("reviewed", statuses)
        self.assertIn("flagged", statuses)

    def test_update_file_status(self):
        """Test updating a file's review status."""
        document = Document.objects.create(
            project=self.project,
            uploaded_by=self.client_user,
            file=SimpleUploadedFile("policy.pdf", b"policy content"),
            original_name="policy.pdf",
            file_size=14,
            status=Document.FileStatus.PENDING_REVIEW,
        )

        resp = self.client.patch(
            f"/api/projects/{self.project.id}/files/{document.id}/",
            data={"status": "approved"},
            content_type="application/json",
            **self.auth_headers,
        )
        self.assertEqual(resp.status_code, 200)
        document.refresh_from_db()
        self.assertEqual(document.status, "approved")

    def test_delete_file_from_project(self):
        """Test deleting a file under a project."""
        document = Document.objects.create(
            project=self.project,
            uploaded_by=self.client_user,
            file=SimpleUploadedFile("temp.txt", b"temp"),
            original_name="temp.txt",
            file_size=4,
        )
        self.assertEqual(self.project.files.count(), 1)

        resp = self.client.delete(
            f"/api/projects/{self.project.id}/files/{document.id}/",
            **self.auth_headers,
        )
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(self.project.files.count(), 0)

    def test_create_project_with_immediate_file_upload(self):
        """Test creating a project and attaching files in the same multipart POST request."""
        sample_file = SimpleUploadedFile(
            name="initial_handbook.pdf",
            content=b"%PDF initial handbook",
            content_type="application/pdf",
        )
        resp = self.client.post(
            "/api/projects/",
            data={
                "name": "Instant Survey",
                "company_name": "Acme Health",
                "status": "active",
                "file": sample_file,
            },
            format="multipart",
            **self.auth_headers,
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()["data"]
        self.assertEqual(data["total_files"], 1)
        self.assertEqual(len(data["files"]), 1)
        self.assertEqual(data["files"][0]["original_name"], "initial_handbook.pdf")


from app.projects.models import (
    ServiceWorkflowTemplate,
    ProjectPhase,
    ProjectTask,
    ProjectStaffAssignment,
)
from app.projects.services_data import SERVICES_LIBRARY
from django.core.management import call_command


class AdminProjectCreationFlowTests(TestCase):
    """
    Tests covering the complete Admin Project Creation Flow:
    - Service workflow template listing.
    - Automated workflow preview with timeline & workload-aware role auto-assignment.
    - Role restrictions: Only Admins/SuperAdmins can generate/create projects from workflow.
    - Multi-service selection generates separate, distinct projects.
    - Staff task updates and QA Reviewer approval workflow.
    """

    def setUp(self):
        call_command("seed_service_templates")

        self.admin = UserAccount.objects.create_user(
            email="lead_admin@example.com",
            password="SecurePassword123!",
            role=UserAccount.Role.ADMIN,
            functional_roles=["Engagement Lead", "Project Manager"],
        )
        self.admin_token = get_tokens_for_user(self.admin)["access"]
        self.admin_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"}

        self.staff_1 = UserAccount.objects.create_user(
            email="architect1@example.com",
            password="SecurePassword123!",
            role=UserAccount.Role.STAFF,
            functional_roles=["Compliance Architect"],
        )
        self.staff_token = get_tokens_for_user(self.staff_1)["access"]
        self.staff_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.staff_token}"}

        self.qa_reviewer = UserAccount.objects.create_user(
            email="qa_lead@example.com",
            password="SecurePassword123!",
            role=UserAccount.Role.QA_REVIEWER,
        )
        self.qa_token = get_tokens_for_user(self.qa_reviewer)["access"]
        self.qa_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.qa_token}"}

        self.client_org = UserAccount.objects.create_user(
            email="director@valleymedical.org",
            password="SecurePassword123!",
            full_name="Valley Medical Center",
            role=UserAccount.Role.CLIENT,
        )

    def test_list_service_workflows(self):
        """Verify listing of predefined service workflow templates."""
        resp = self.client.get("/api/projects/service-workflows/", **self.admin_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertGreaterEqual(data["count"], 5)
        slugs = [s["slug"] for s in data["data"]]
        self.assertIn("carf-initial", slugs)
        self.assertIn("mock-survey", slugs)

    def test_preview_workflow_admin_success(self):
        """Admin generates workflow preview with calculated dates and auto-assigned staff."""
        resp = self.client.post(
            "/api/projects/preview-workflow/",
            data={
                "service_slug": "carf-initial",
                "client_id": str(self.client_org.id),
                "client_name": "Valley Medical Center",
                "start_date": "2026-05-01",
            },
            content_type="application/json",
            **self.admin_headers,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["service_slug"], "carf-initial")
        self.assertEqual(data["duration_weeks"], 12)
        self.assertEqual(data["start_date"], "2026-05-01")
        self.assertEqual(data["target_end_date"], "2026-07-24")
        self.assertGreater(len(data["phases"]), 0)

        # Check that Compliance Architect role was auto-assigned to staff_1
        ca_assigned = data["role_assignments"].get("Compliance Architect")
        self.assertIsNotNone(ca_assigned)
        self.assertEqual(ca_assigned["email"], self.staff_1.email)

    def test_preview_and_create_restricted_from_staff(self):
        """Staff members are forbidden from previewing or creating client projects."""
        resp_preview = self.client.post(
            "/api/projects/preview-workflow/",
            data={"service_slug": "carf-initial"},
            content_type="application/json",
            **self.staff_headers,
        )
        self.assertEqual(resp_preview.status_code, 403)

        resp_create = self.client.post(
            "/api/projects/create-from-workflow/",
            data={
                "client_id": str(self.client_org.id),
                "service_slugs": ["carf-initial"],
            },
            content_type="application/json",
            **self.staff_headers,
        )
        self.assertEqual(resp_create.status_code, 403)

    def test_create_project_single_service(self):
        """Admin creates a single project from a service workflow."""
        resp = self.client.post(
            "/api/projects/create-from-workflow/",
            data={
                "client_id": str(self.client_org.id),
                "company_name": "Valley Medical Center",
                "service_slugs": ["carf-initial"],
                "start_date": "2026-05-01",
                "project_name": "Valley Medical - CARF Survey Prep",
                "custom_tasks": [
                    {
                        "title": "Initial Kickoff Stakeholder Call",
                        "responsible_role": "Engagement Lead",
                        "due_date": "2026-05-05",
                        "deliverables": ["Kickoff Presentation Deck"],
                    }
                ],
            },
            content_type="application/json",
            **self.admin_headers,
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()["data"]
        self.assertEqual(len(data), 1)

        project = Project.objects.get(id=data[0]["id"])
        self.assertEqual(project.name, "Valley Medical - CARF Survey Prep")
        self.assertEqual(project.company_name, "Valley Medical Center")
        self.assertEqual(project.owner, self.client_org)

        # Check phases and tasks were populated
        self.assertGreaterEqual(project.phases.count(), 5)
        self.assertGreaterEqual(project.tasks.count(), 10)

        # Check staff assignment
        self.assertTrue(project.staff_assignments.filter(staff=self.staff_1).exists())

        # Check custom task was inserted
        custom_task = project.tasks.filter(is_custom=True).first()
        self.assertIsNotNone(custom_task)
        self.assertEqual(custom_task.title, "Initial Kickoff Stakeholder Call")

    def test_multi_service_selection_creates_separate_projects(self):
        """Selecting multiple services creates distinct, separate projects."""
        resp = self.client.post(
            "/api/projects/create-from-workflow/",
            data={
                "client_id": str(self.client_org.id),
                "company_name": "Valley Medical Center",
                "service_slugs": ["carf-initial", "mock-survey", "cap-development"],
                "start_date": "2026-06-01",
            },
            content_type="application/json",
            **self.admin_headers,
        )
        self.assertEqual(resp.status_code, 201)
        created_projects = resp.json()["data"]
        self.assertEqual(len(created_projects), 3)

        project_ids = [p["id"] for p in created_projects]
        projects_in_db = Project.objects.filter(id__in=project_ids)
        self.assertEqual(projects_in_db.count(), 3)

        slugs = [p.service_template.slug for p in projects_in_db]
        self.assertIn("carf-initial", slugs)
        self.assertIn("mock-survey", slugs)
        self.assertIn("cap-development", slugs)

    def test_task_submission_and_qa_review_workflow(self):
        """Staff submits task deliverables for QA, QA Reviewer approves."""
        # Create project first
        resp = self.client.post(
            "/api/projects/create-from-workflow/",
            data={
                "client_id": str(self.client_org.id),
                "service_slugs": ["mock-survey"],
                "start_date": "2026-05-01",
            },
            content_type="application/json",
            **self.admin_headers,
        )
        project_id = resp.json()["data"][0]["id"]
        task = ProjectTask.objects.filter(project_id=project_id, responsible_role="Compliance Architect").first()
        self.assertIsNotNone(task)

        # Reassign to staff_1
        task.assigned_to = self.staff_1
        task.save()

        # Staff updates task & submits for QA
        update_resp = self.client.patch(
            f"/api/projects/tasks/{task.id}/",
            data={
                "status": "submitted_for_qa",
                "submission_notes": "Desk audit completed and evidence checklist attached.",
            },
            content_type="application/json",
            **self.staff_headers,
        )
        self.assertEqual(update_resp.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, ProjectTask.TaskStatus.SUBMITTED_FOR_QA)
        self.assertEqual(task.qa_status, ProjectTask.QAStatus.UNDER_REVIEW)

        # QA Reviewer approves task
        qa_resp = self.client.post(
            f"/api/projects/tasks/{task.id}/qa-review/",
            data={"action": "approve", "notes": "Approved. Documentation meets CARF standard ASPIRE 1.A."},
            content_type="application/json",
            **self.qa_headers,
        )
        self.assertEqual(qa_resp.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, ProjectTask.TaskStatus.COMPLETED)
        self.assertEqual(task.qa_status, ProjectTask.QAStatus.APPROVED)
        self.assertEqual(task.qa_reviewer, self.qa_reviewer)

