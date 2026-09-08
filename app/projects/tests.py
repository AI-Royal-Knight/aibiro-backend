import io
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from app.accounts.models import UserAccount
from app.accounts.views import get_tokens_for_user
from app.projects.models import Project, ProjectFile


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


class ProjectFileUploadTests(TestCase):
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

    def test_list_project_files(self):
        """Test retrieving all files under a project."""
        ProjectFile.objects.create(
            project=self.project,
            uploaded_by=self.client_user,
            file=SimpleUploadedFile("doc1.pdf", b"pdf content"),
            original_name="doc1.pdf",
            file_size=11,
            status=ProjectFile.FileStatus.REVIEWED,
        )
        ProjectFile.objects.create(
            project=self.project,
            uploaded_by=self.client_user,
            file=SimpleUploadedFile("doc2.xlsx", b"xlsx content"),
            original_name="doc2.xlsx",
            file_size=12,
            status=ProjectFile.FileStatus.FLAGGED,
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
        project_file = ProjectFile.objects.create(
            project=self.project,
            uploaded_by=self.client_user,
            file=SimpleUploadedFile("policy.pdf", b"policy content"),
            original_name="policy.pdf",
            file_size=14,
            status=ProjectFile.FileStatus.PENDING_REVIEW,
        )

        resp = self.client.patch(
            f"/api/projects/{self.project.id}/files/{project_file.id}/",
            data={"status": "approved"},
            content_type="application/json",
            **self.auth_headers,
        )
        self.assertEqual(resp.status_code, 200)
        project_file.refresh_from_db()
        self.assertEqual(project_file.status, "approved")

    def test_delete_file_from_project(self):
        """Test deleting a file under a project."""
        project_file = ProjectFile.objects.create(
            project=self.project,
            uploaded_by=self.client_user,
            file=SimpleUploadedFile("temp.txt", b"temp"),
            original_name="temp.txt",
            file_size=4,
        )
        self.assertEqual(self.project.files.count(), 1)

        resp = self.client.delete(
            f"/api/projects/{self.project.id}/files/{project_file.id}/",
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
