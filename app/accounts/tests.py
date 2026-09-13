from datetime import timedelta
from unittest.mock import patch
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from app.accounts.models import OTP, PasswordChangeHistory, UserAccount
from app.accounts.utils import send_otp_email


class UserAccountModelTests(TestCase):
    def test_create_user_successful(self):
        """Test creating a basic user with email, password, and full name."""
        user = UserAccount.objects.create_user(
            email="John.Doe@Example.COM  ",
            password="SecurePassword123!",
            full_name="John Doe",
        )
        self.assertEqual(user.email, "john.doe@example.com")
        self.assertTrue(user.check_password("SecurePassword123!"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertEqual(user.role, UserAccount.Role.USER)
        # Check UUID inheritance
        self.assertIsNotNone(user.id)
        # Check auto-generated username
        self.assertEqual(user.username, "john.doe")

    def test_create_user_without_email_raises_error(self):
        """Test that create_user raises ValueError if email is missing."""
        with self.assertRaises(ValueError):
            UserAccount.objects.create_user(email="", password="password123")

    def test_create_superuser_successful(self):
        """Test creating a superuser with admin privileges."""
        admin = UserAccount.objects.create_superuser(
            email="admin@example.com",
            password="AdminPassword123!",
            full_name="Super Admin",
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_active)
        self.assertEqual(admin.role, UserAccount.Role.SUPER_ADMIN)

    def test_username_auto_generation_uniqueness(self):
        """Test that duplicate email prefixes receive an incremented unique username."""
        u1 = UserAccount.objects.create_user(email="testuser@example.com", password="pwd")
        u2 = UserAccount.objects.create_user(email="testuser@otherdomain.com", password="pwd")
        self.assertEqual(u1.username, "testuser")
        self.assertEqual(u2.username, "testuser1")

    def test_oauth_user_validation(self):
        """Test that OAuth users require provider_uid."""
        user = UserAccount(
            email="googleuser@example.com",
            auth_provider=UserAccount.AuthProvider.GOOGLE,
            provider_uid=None,
        )
        with self.assertRaises(ValidationError):
            user.clean()


class OTPModelTests(TestCase):
    def setUp(self):
        self.user = UserAccount.objects.create_user(
            email="otpuser@example.com",
            password="password123",
            full_name="OTP User",
        )

    def test_otp_is_valid_and_expired(self):
        """Test OTP validity window."""
        otp = OTP.objects.create(user=self.user, otp_hash="fake_hash_123")
        self.assertTrue(otp.is_valid(expiry_minutes=5))
        self.assertFalse(otp.is_expired(expiry_minutes=5))

        # Test past expiration
        otp.created_at = timezone.now() - timedelta(minutes=10)
        otp.save()
        self.assertFalse(otp.is_valid(expiry_minutes=5))
        self.assertTrue(otp.is_expired(expiry_minutes=5))


class EmailVerificationTemplateTests(TestCase):
    def setUp(self):
        self.user = UserAccount.objects.create_user(
            email="doctor.smith@accredisure.com",
            password="SecurePassword123!",
            first_name="Alexander",
            last_name="Smith",
            full_name="Alexander Smith",
        )

    def test_send_otp_email_renders_branded_html_and_text(self):
        """Test that send_otp_email sends rich AccrediSure HTML email with OTP digits and fallback."""
        success = send_otp_email(self.user, "592814", purpose="signup")
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)

        sent_mail = mail.outbox[0]
        self.assertIn("592814", sent_mail.subject)
        self.assertIn("AccrediSure", sent_mail.subject)
        self.assertEqual(sent_mail.to, ["doctor.smith@accredisure.com"])

        # Check plain text content
        self.assertIn("592814", sent_mail.body)
        self.assertIn("AccrediSure", sent_mail.body)
        self.assertIn("Alexander", sent_mail.body)

        # Check HTML alternative
        self.assertTrue(len(sent_mail.alternatives) > 0)
        html_content, content_type = sent_mail.alternatives[0]
        self.assertEqual(content_type, "text/html")
        self.assertIn("AccrediSure", html_content)
        self.assertIn("Healthcare Compliance &amp; Accreditation", html_content)
        self.assertIn("592814", html_content)
        self.assertIn("Alexander", html_content)
        self.assertIn("#1A1611", html_content)  # Brand obsidian color
        self.assertIn("#B18F56", html_content)  # Brand accent gold color

    def test_email_preview_endpoint_in_debug_mode(self):
        """Test GET /api/auth/preview-email/ renders preview template when DEBUG=True."""
        with self.settings(DEBUG=True):
            response = self.client.get("/api/auth/preview-email/?otp=928410&name=Sarah")
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/html", response["Content-Type"])
            html = response.content.decode("utf-8")
            self.assertIn("928410", html)
            self.assertIn("AccrediSure", html)
            self.assertIn("Sarah", html)


class AuthViewTests(TestCase):
    def test_signup_success_creates_user_and_otp(self):
        """Test POST /api/auth/register/ creates account and generates OTP."""
        payload = {
            "first_name": "Sarah",
            "last_name": "Connor",
            "full_name": "Sarah Connor",
            "email": "sarah@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        }
        response = self.client.post("/api/auth/register/", data=payload, content_type="application/json")
        self.assertEqual(response.status_code, 201)

        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("verification code", data["message"])
        self.assertEqual(data["data"]["email"], "sarah@example.com")

        # Verify user was saved and OTP was created
        user = UserAccount.objects.get(email="sarah@example.com")
        self.assertFalse(user.is_verified)
        self.assertTrue(user.otps.filter(is_used=False).exists())

    def test_signup_password_mismatch_returns_400(self):
        """Test POST /api/auth/register/ rejects mismatched passwords."""
        payload = {
            "first_name": "Test",
            "last_name": "User",
            "full_name": "Test User",
            "email": "mismatch@example.com",
            "password": "Password123!",
            "confirm_password": "DifferentPassword123!",
        }
        response = self.client.post("/api/auth/register/", data=payload, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("confirm_password", response.json())

    def test_signup_duplicate_email_returns_400(self):
        """Test POST /api/auth/register/ rejects already registered email."""
        UserAccount.objects.create_user(email="existing@example.com", password="Password123!", is_verified=True)
        payload = {
            "first_name": "Duplicate",
            "last_name": "User",
            "full_name": "Duplicate User",
            "email": "existing@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        }
        response = self.client.post("/api/auth/register/", data=payload, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json())

    def test_verify_otp_success_returns_jwt_tokens(self):
        """Test POST /api/auth/verify-otp/ with valid code activates account and returns tokens."""
        from app.accounts.utils import create_otp_for_user

        user = UserAccount.objects.create_user(
            email="verifytest@example.com",
            password="Password123!",
            full_name="Verify Test",
            is_verified=False,
        )
        _, raw_otp = create_otp_for_user(user)

        payload = {
            "email": "verifytest@example.com",
            "otp": raw_otp,
        }
        response = self.client.post("/api/auth/verify-otp/", data=payload, content_type="application/json")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("tokens", data)
        self.assertIn("access", data["tokens"])
        self.assertIn("refresh", data["tokens"])
        self.assertTrue(data["user"]["is_verified"])

        # Check DB update
        user.refresh_from_db()
        self.assertTrue(user.is_verified)
        self.assertFalse(user.otps.filter(is_used=False).exists())

    def test_verify_otp_invalid_code_returns_400(self):
        """Test POST /api/auth/verify-otp/ with incorrect code fails."""
        from app.accounts.utils import create_otp_for_user

        user = UserAccount.objects.create_user(
            email="invalidotp@example.com",
            password="Password123!",
            is_verified=False,
        )
        create_otp_for_user(user)

        payload = {
            "email": "invalidotp@example.com",
            "otp": "000000",
        }
        response = self.client.post("/api/auth/verify-otp/", data=payload, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])

    def test_resend_otp_generates_new_code(self):
        """Test POST /api/auth/resend-otp/ sends a new OTP."""
        user = UserAccount.objects.create_user(
            email="resend@example.com",
            password="Password123!",
            is_verified=False,
        )
        response = self.client.post(
            "/api/auth/resend-otp/",
            data={"email": "resend@example.com"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(user.otps.filter(is_used=False).exists())

    def test_login_success_and_profile_access(self):
        """Test POST /api/auth/login/ returns JWT tokens to authenticate subsequent requests."""
        UserAccount.objects.create_user(
            email="logintest@example.com",
            password="Password123!",
            full_name="Login Test",
            is_active=True,
            is_verified=True,
        )
        login_resp = self.client.post(
            "/api/auth/login/",
            data={"email": "logintest@example.com", "password": "Password123!"},
            content_type="application/json",
        )
        self.assertEqual(login_resp.status_code, 200)
        access_token = login_resp.json()["tokens"]["access"]

        # Test authenticated profile access
        profile_resp = self.client.get(
            "/api/auth/profile/",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        self.assertEqual(profile_resp.status_code, 200)
        self.assertEqual(profile_resp.json()["email"], "logintest@example.com")

    def test_update_profile_settings(self):
        """Test updating First Name, Last Name, Phone Number, and Job Title."""
        user = UserAccount.objects.create_user(
            email="settingsuser@example.com",
            password="Password123!",
            is_active=True,
            is_verified=True,
        )
        from app.accounts.views import get_tokens_for_user
        tokens = get_tokens_for_user(user)

        payload = {
            "first_name": "John",
            "last_name": "Doe",
            "phone_number": "+1 (555) 123-4567",
            "job_title": "CEO & Founder",
        }
        resp = self.client.patch(
            "/api/auth/profile/settings/",
            data=payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {tokens['access']}",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["user"]["first_name"], "John")
        self.assertEqual(data["user"]["last_name"], "Doe")
        self.assertEqual(data["user"]["full_name"], "John Doe")
        self.assertEqual(data["user"]["phone_number"], "+1 (555) 123-4567")
        self.assertEqual(data["user"]["job_title"], "CEO & Founder")

        user.refresh_from_db()
        self.assertEqual(user.full_name, "John Doe")
        self.assertEqual(user.job_title, "CEO & Founder")

    def test_logout_blacklists_refresh_token(self):
        """Test POST /api/auth/logout/ blacklists the refresh token."""
        user = UserAccount.objects.create_user(
            email="logouttest@example.com",
            password="Password123!",
            is_active=True,
            is_verified=True,
        )
        from app.accounts.views import get_tokens_for_user
        tokens = get_tokens_for_user(user)

        # Logout with refresh token
        logout_resp = self.client.post(
            "/api/auth/logout/",
            data={"refresh": tokens["refresh"]},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {tokens['access']}",
        )
        self.assertEqual(logout_resp.status_code, 200)
        self.assertTrue(logout_resp.json()["success"])

        # Subsequent attempt to refresh using the blacklisted token should fail
        refresh_resp = self.client.post(
            "/api/auth/token/refresh/",
            data={"refresh": tokens["refresh"]},
            content_type="application/json",
        )
        self.assertEqual(refresh_resp.status_code, 401)

    def test_password_update_success(self):
        """Test POST /api/auth/security/password/ updates user password and allows login with new password."""
        user = UserAccount.objects.create_user(
            email="pwduser@example.com",
            password="OldPassword123!",
            is_active=True,
            is_verified=True,
        )
        from app.accounts.views import get_tokens_for_user
        tokens = get_tokens_for_user(user)

        payload = {
            "current_password": "OldPassword123!",
            "new_password": "NewSecurePassword456!",
            "confirm_new_password": "NewSecurePassword456!",
        }
        resp = self.client.post(
            "/api/auth/security/password/",
            data=payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {tokens['access']}",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])

        # Check that login works with new password
        login_resp = self.client.post(
            "/api/auth/login/",
            data={"email": "pwduser@example.com", "password": "NewSecurePassword456!"},
            content_type="application/json",
        )
        self.assertEqual(login_resp.status_code, 200)

    def test_password_update_wrong_current_password_fails(self):
        """Test password update rejects incorrect current password."""
        user = UserAccount.objects.create_user(
            email="pwduser2@example.com",
            password="OldPassword123!",
            is_active=True,
            is_verified=True,
        )
        from app.accounts.views import get_tokens_for_user
        tokens = get_tokens_for_user(user)

        payload = {
            "current_password": "WrongPassword999!",
            "new_password": "NewSecurePassword456!",
            "confirm_new_password": "NewSecurePassword456!",
        }
        resp = self.client.post(
            "/api/auth/security/password/",
            data=payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {tokens['access']}",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("current_password", resp.json())

    def test_two_factor_toggle_and_login_challenge(self):
        """Test enabling 2FA triggers OTP requirement upon subsequent login."""
        user = UserAccount.objects.create_user(
            email="twofa@example.com",
            password="Password123!",
            is_active=True,
            is_verified=True,
        )
        from app.accounts.views import get_tokens_for_user
        tokens = get_tokens_for_user(user)

        # 1. Enable 2FA
        resp = self.client.post(
            "/api/auth/security/2fa/",
            data={"enable": True, "method": "email"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {tokens['access']}",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["data"]["two_factor_enabled"])

        # 2. Login now triggers 2FA challenge
        login_resp = self.client.post(
            "/api/auth/login/",
            data={"email": "twofa@example.com", "password": "Password123!"},
            content_type="application/json",
        )
        self.assertEqual(login_resp.status_code, 200)
        login_data = login_resp.json()
        self.assertTrue(login_data["two_factor_required"])
        self.assertNotIn("tokens", login_data)

        # 3. Disable 2FA
        disable_resp = self.client.post(
            "/api/auth/security/2fa/",
            data={"enable": False},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {tokens['access']}",
        )
        self.assertEqual(disable_resp.status_code, 200)
        self.assertFalse(disable_resp.json()["data"]["two_factor_enabled"])


class PasswordChangeHistoryTests(TestCase):
    def setUp(self):
        self.user = UserAccount.objects.create_user(
            email="historyuser@example.com",
            password="OldPassword123!",
            full_name="History Tester",
            is_active=True,
            is_verified=True,
        )
        from app.accounts.views import get_tokens_for_user

        tokens = get_tokens_for_user(self.user)
        self.access_token = tokens["access"]
        self.auth_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.access_token}"}

    def test_password_update_success_records_history(self):
        """Test that a successful password update creates a SUCCESS history record with device and location."""
        resp = self.client.post(
            "/api/auth/security/password/",
            data={
                "current_password": "OldPassword123!",
                "new_password": "BrandNewPassword123!",
                "confirm_new_password": "BrandNewPassword123!",
            },
            content_type="application/json",
            HTTP_USER_AGENT="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            HTTP_X_CLIENT_LOCATION="Lisbon, Portugal",
            **self.auth_headers,
        )
        self.assertEqual(resp.status_code, 200)

        history = PasswordChangeHistory.objects.filter(user=self.user)
        self.assertEqual(history.count(), 1)
        record = history.first()
        self.assertEqual(record.status, PasswordChangeHistory.Status.SUCCESS)
        self.assertEqual(record.device_info, "MacBook Pro (Mac OS)")
        self.assertEqual(record.location, "Lisbon, Portugal")

    def test_password_update_failed_records_history(self):
        """Test that a failed password update attempt creates a FAILED history record."""
        resp = self.client.post(
            "/api/auth/security/password/",
            data={
                "current_password": "WrongPassword123!",
                "new_password": "BrandNewPassword123!",
                "confirm_new_password": "BrandNewPassword123!",
            },
            content_type="application/json",
            HTTP_USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            HTTP_X_CLIENT_LOCATION="Porto, Portugal",
            **self.auth_headers,
        )
        self.assertEqual(resp.status_code, 400)

        history = PasswordChangeHistory.objects.filter(user=self.user)
        self.assertEqual(history.count(), 1)
        record = history.first()
        self.assertEqual(record.status, PasswordChangeHistory.Status.FAILED)
        self.assertEqual(record.device_info, "Windows PC (Windows 11)")
        self.assertEqual(record.location, "Porto, Portugal")

    def test_get_password_change_history_endpoint(self):
        """Test retrieving the list of password change history records matching the UI."""
        PasswordChangeHistory.objects.create(
            user=self.user,
            status=PasswordChangeHistory.Status.SUCCESS,
            device_info="MacBook Pro (Mac OS)",
            location="Lisbon, Portugal",
        )
        PasswordChangeHistory.objects.create(
            user=self.user,
            status=PasswordChangeHistory.Status.FAILED,
            device_info="Windows PC (Windows 11)",
            location="Porto, Portugal",
        )

        resp = self.client.get(
            "/api/auth/security/password-history/",
            **self.auth_headers,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = data.get("results", data)
        self.assertEqual(len(results), 2)

        first_item = results[0]
        self.assertIn("formatted_date", first_item)
        self.assertIn("device_summary", first_item)
        self.assertIn("status_display", first_item)
        self.assertIn(first_item["status_display"], ["Success", "Failed Attempt"])

    def test_history_isolated_per_user(self):
        """Test that users can only see their own password change history."""
        other_user = UserAccount.objects.create_user(
            email="otheruser@example.com",
            password="OtherPassword123!",
        )
        PasswordChangeHistory.objects.create(
            user=other_user,
            status=PasswordChangeHistory.Status.SUCCESS,
            device_info="iPhone 13 (iOS)",
            location="Lisbon, Portugal",
        )

        resp = self.client.get(
            "/api/auth/security/password-history/",
            **self.auth_headers,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = data.get("results", data)
        self.assertEqual(len(results), 0)

    def test_get_password_history_unauthenticated_returns_401(self):
        """Test that unauthenticated requests to password history are unauthorized."""
        resp = self.client.get("/api/auth/security/password-history/")
        self.assertEqual(resp.status_code, 401)


class RBACPermissionsTests(TestCase):
    """Unit tests for RBAC role properties, hierarchy, and permission classes."""

    def setUp(self):
        self.super_admin = UserAccount.objects.create_user(
            email="superadmin@example.com",
            password="Password123!",
            role=UserAccount.Role.SUPER_ADMIN,
        )
        self.admin = UserAccount.objects.create_user(
            email="admin@example.com",
            password="Password123!",
            role=UserAccount.Role.ADMIN,
        )
        self.staff = UserAccount.objects.create_user(
            email="staff@example.com",
            password="Password123!",
            role=UserAccount.Role.STAFF,
        )
        self.qa = UserAccount.objects.create_user(
            email="qa@example.com",
            password="Password123!",
            role=UserAccount.Role.QA_REVIEWER,
        )
        self.client_user = UserAccount.objects.create_user(
            email="client@example.com",
            password="Password123!",
            role=UserAccount.Role.CLIENT,
        )

    def test_all_five_roles_created_with_correct_properties(self):
        # Super Admin
        self.assertTrue(self.super_admin.is_super_admin)
        self.assertTrue(self.super_admin.is_admin_user)
        self.assertTrue(self.super_admin.is_staff_member)
        self.assertTrue(self.super_admin.is_qa_reviewer)
        self.assertFalse(self.super_admin.is_client)

        # Admin
        self.assertFalse(self.admin.is_super_admin)
        self.assertTrue(self.admin.is_admin_user)
        self.assertTrue(self.admin.is_staff_member)
        self.assertTrue(self.admin.is_qa_reviewer)
        self.assertFalse(self.admin.is_client)

        # Staff
        self.assertFalse(self.staff.is_super_admin)
        self.assertFalse(self.staff.is_admin_user)
        self.assertTrue(self.staff.is_staff_member)
        self.assertFalse(self.staff.is_qa_reviewer)
        self.assertFalse(self.staff.is_client)

        # QA Reviewer
        self.assertFalse(self.qa.is_super_admin)
        self.assertFalse(self.qa.is_admin_user)
        self.assertFalse(self.qa.is_staff_member)
        self.assertTrue(self.qa.is_qa_reviewer)
        self.assertFalse(self.qa.is_client)

        # Client
        self.assertFalse(self.client_user.is_super_admin)
        self.assertFalse(self.client_user.is_admin_user)
        self.assertFalse(self.client_user.is_staff_member)
        self.assertFalse(self.client_user.is_qa_reviewer)
        self.assertTrue(self.client_user.is_client)

    def test_role_hierarchy_checks(self):
        # Super Admin >= all
        for role in UserAccount.Role.values:
            self.assertTrue(self.super_admin.has_role_or_higher(role))

        # Admin >= Staff, QA, Client
        self.assertTrue(self.admin.has_role_or_higher(UserAccount.Role.ADMIN))
        self.assertTrue(self.admin.has_role_or_higher(UserAccount.Role.STAFF))
        self.assertTrue(self.admin.has_role_or_higher(UserAccount.Role.QA_REVIEWER))
        self.assertTrue(self.admin.has_role_or_higher(UserAccount.Role.CLIENT))
        self.assertFalse(self.admin.has_role_or_higher(UserAccount.Role.SUPER_ADMIN))

        # Staff >= Staff, QA, Client
        self.assertTrue(self.staff.has_role_or_higher(UserAccount.Role.STAFF))
        self.assertTrue(self.staff.has_role_or_higher(UserAccount.Role.QA_REVIEWER))
        self.assertTrue(self.staff.has_role_or_higher(UserAccount.Role.CLIENT))
        self.assertFalse(self.staff.has_role_or_higher(UserAccount.Role.ADMIN))

        # QA Reviewer >= QA, Client
        self.assertTrue(self.qa.has_role_or_higher(UserAccount.Role.QA_REVIEWER))
        self.assertTrue(self.qa.has_role_or_higher(UserAccount.Role.CLIENT))
        self.assertFalse(self.qa.has_role_or_higher(UserAccount.Role.STAFF))

        # Client >= Client only
        self.assertTrue(self.client_user.has_role_or_higher(UserAccount.Role.CLIENT))
        self.assertFalse(self.client_user.has_role_or_higher(UserAccount.Role.QA_REVIEWER))

    def test_drf_permission_classes(self):
        from app.common.permissions import (
            HasRole,
            HasRoleOrHigher,
            IsAdmin,
            IsClient,
            IsQAReviewer,
            IsStaff,
            IsSuperAdmin,
            RolePermission,
        )

        class MockRequest:
            def __init__(self, user):
                self.user = user

        class MockView:
            allowed_roles = [UserAccount.Role.QA_REVIEWER, UserAccount.Role.STAFF]

        # IsSuperAdmin
        perm = IsSuperAdmin()
        self.assertTrue(perm.has_permission(MockRequest(self.super_admin), None))
        self.assertFalse(perm.has_permission(MockRequest(self.admin), None))
        self.assertFalse(perm.has_permission(MockRequest(self.client_user), None))

        # IsAdmin
        perm = IsAdmin()
        self.assertTrue(perm.has_permission(MockRequest(self.super_admin), None))
        self.assertTrue(perm.has_permission(MockRequest(self.admin), None))
        self.assertFalse(perm.has_permission(MockRequest(self.staff), None))

        # IsStaff
        perm = IsStaff()
        self.assertTrue(perm.has_permission(MockRequest(self.super_admin), None))
        self.assertTrue(perm.has_permission(MockRequest(self.admin), None))
        self.assertTrue(perm.has_permission(MockRequest(self.staff), None))
        self.assertFalse(perm.has_permission(MockRequest(self.client_user), None))

        # IsQAReviewer
        perm = IsQAReviewer()
        self.assertTrue(perm.has_permission(MockRequest(self.super_admin), None))
        self.assertTrue(perm.has_permission(MockRequest(self.admin), None))
        self.assertTrue(perm.has_permission(MockRequest(self.qa), None))
        self.assertFalse(perm.has_permission(MockRequest(self.client_user), None))

        # IsClient
        perm = IsClient()
        self.assertTrue(perm.has_permission(MockRequest(self.client_user), None))
        self.assertFalse(perm.has_permission(MockRequest(self.super_admin), None))

        # RolePermission with allowed_roles
        perm = RolePermission()
        view = MockView()
        self.assertTrue(perm.has_permission(MockRequest(self.super_admin), view))
        self.assertTrue(perm.has_permission(MockRequest(self.staff), view))
        self.assertTrue(perm.has_permission(MockRequest(self.qa), view))
        self.assertFalse(perm.has_permission(MockRequest(self.client_user), view))

        # HasRole
        custom_perm = HasRole(UserAccount.Role.STAFF, UserAccount.Role.CLIENT)()
        self.assertTrue(custom_perm.has_permission(MockRequest(self.staff), None))
        self.assertTrue(custom_perm.has_permission(MockRequest(self.client_user), None))
        self.assertFalse(custom_perm.has_permission(MockRequest(self.qa), None))

        # HasRoleOrHigher
        hierarchy_perm = HasRoleOrHigher(UserAccount.Role.STAFF)()
        self.assertTrue(hierarchy_perm.has_permission(MockRequest(self.super_admin), None))
        self.assertTrue(hierarchy_perm.has_permission(MockRequest(self.admin), None))
        self.assertTrue(hierarchy_perm.has_permission(MockRequest(self.staff), None))
        self.assertFalse(hierarchy_perm.has_permission(MockRequest(self.client_user), None))


class UserRoleManagementApiTests(TestCase):
    """Integration tests for User Role Management endpoints and JWT role claims."""

    def setUp(self):
        self.super_admin = UserAccount.objects.create_user(
            email="superadmin@example.com",
            password="Password123!",
            role=UserAccount.Role.SUPER_ADMIN,
        )
        self.admin = UserAccount.objects.create_user(
            email="admin@example.com",
            password="Password123!",
            role=UserAccount.Role.ADMIN,
        )
        self.staff = UserAccount.objects.create_user(
            email="staff@example.com",
            password="Password123!",
            role=UserAccount.Role.STAFF,
        )
        self.target_client = UserAccount.objects.create_user(
            email="targetclient@example.com",
            password="Password123!",
            role=UserAccount.Role.CLIENT,
        )

        from app.accounts.views import get_tokens_for_user
        self.super_admin_token = get_tokens_for_user(self.super_admin)["access"]
        self.admin_token = get_tokens_for_user(self.admin)["access"]
        self.staff_token = get_tokens_for_user(self.staff)["access"]
        self.client_token = get_tokens_for_user(self.target_client)["access"]

    def test_jwt_token_contains_role_claim(self):
        """Test that the issued JWT tokens include the role claim."""
        from rest_framework_simplejwt.tokens import AccessToken
        token = AccessToken(self.super_admin_token)
        self.assertEqual(token["role"], UserAccount.Role.SUPER_ADMIN)

        client_token = AccessToken(self.client_token)
        self.assertEqual(client_token["role"], UserAccount.Role.CLIENT)

    def test_list_users_accessible_by_admin_and_super_admin(self):
        """Test user listing endpoint is accessible to admins and filterable."""
        # Super Admin access
        resp = self.client.get(
            "/api/auth/users/",
            HTTP_AUTHORIZATION=f"Bearer {self.super_admin_token}",
        )
        self.assertEqual(resp.status_code, 200)

        # Admin access
        resp = self.client.get(
            "/api/auth/users/?role=client",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = data.get("results", data)
        for u in results:
            self.assertEqual(u["role"], "client")

    def test_list_users_forbidden_for_staff_and_client(self):
        """Staff and Client roles cannot access user listing."""
        resp = self.client.get(
            "/api/auth/users/",
            HTTP_AUTHORIZATION=f"Bearer {self.staff_token}",
        )
        self.assertEqual(resp.status_code, 403)

        resp = self.client.get(
            "/api/auth/users/",
            HTTP_AUTHORIZATION=f"Bearer {self.client_token}",
        )
        self.assertEqual(resp.status_code, 403)

    def test_super_admin_can_update_user_role(self):
        """Super Admin can update any user to any valid role."""
        resp = self.client.patch(
            f"/api/auth/users/{self.target_client.id}/role/",
            data={"role": UserAccount.Role.QA_REVIEWER},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.super_admin_token}",
        )
        self.assertEqual(resp.status_code, 200)
        self.target_client.refresh_from_db()
        self.assertEqual(self.target_client.role, UserAccount.Role.QA_REVIEWER)

    def test_admin_cannot_promote_to_super_admin(self):
        """Admin is forbidden from assigning the Super Admin role."""
        resp = self.client.patch(
            f"/api/auth/users/{self.target_client.id}/role/",
            data={"role": UserAccount.Role.SUPER_ADMIN},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Only Super Admins can assign the Super Admin role.", str(resp.json()))

    def test_admin_cannot_modify_super_admin_account(self):
        """Admin is forbidden from modifying a Super Admin account."""
        resp = self.client.patch(
            f"/api/auth/users/{self.super_admin.id}/role/",
            data={"role": UserAccount.Role.STAFF},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )
        self.assertEqual(resp.status_code, 403)
        self.super_admin.refresh_from_db()
        self.assertEqual(self.super_admin.role, UserAccount.Role.SUPER_ADMIN)

    def test_client_cannot_update_roles(self):
        """Client receives 403 when attempting to modify roles."""
        resp = self.client.patch(
            f"/api/auth/users/{self.target_client.id}/role/",
            data={"role": UserAccount.Role.ADMIN},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.client_token}",
        )
        self.assertEqual(resp.status_code, 403)


class GoogleAuthApiTests(TestCase):
    """Integration tests for Google OAuth authentication endpoint /api/auth/google/."""

    def test_google_auth_requires_token(self):
        """Returns 400 when neither id_token nor access_token is provided."""
        resp = self.client.post(
            "/api/auth/google/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    @patch("app.accounts.views.verify_google_token")
    def test_google_auth_creates_new_client_account(self, mock_verify):
        """New Google user is created with Role.CLIENT and is_verified=True."""
        mock_verify.return_value = {
            "sub": "google-uid-12345",
            "email": "newgoogleuser@example.com",
            "first_name": "Google",
            "last_name": "User",
            "full_name": "Google User",
            "picture": "https://example.com/avatar.jpg",
        }

        resp = self.client.post(
            "/api/auth/google/",
            data={"id_token": "valid-id-token"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("tokens", data)
        self.assertIn("access", data["tokens"])
        self.assertEqual(data["user"]["email"], "newgoogleuser@example.com")
        self.assertEqual(data["user"]["role"], UserAccount.Role.CLIENT)
        self.assertTrue(data["user"]["is_verified"])

        user = UserAccount.objects.get(email="newgoogleuser@example.com")
        self.assertEqual(user.auth_provider, UserAccount.AuthProvider.GOOGLE)
        self.assertEqual(user.provider_uid, "google-uid-12345")
        self.assertTrue(user.is_verified)

    @patch("app.accounts.views.verify_google_token")
    def test_google_auth_links_existing_user(self, mock_verify):
        """Existing email user logging in with Google is linked and verified."""
        existing_user = UserAccount.objects.create_user(
            email="existing@example.com",
            password="Password123!",
            role=UserAccount.Role.CLIENT,
            is_verified=False,
        )

        mock_verify.return_value = {
            "sub": "google-uid-99999",
            "email": "existing@example.com",
            "first_name": "Existing",
            "last_name": "User",
            "full_name": "Existing User",
            "picture": "",
        }

        resp = self.client.post(
            "/api/auth/google/",
            data={"access_token": "valid-access-token"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        existing_user.refresh_from_db()
        self.assertEqual(existing_user.provider_uid, "google-uid-99999")
        self.assertEqual(existing_user.auth_provider, UserAccount.AuthProvider.GOOGLE)
        self.assertTrue(existing_user.is_verified)

    @patch("app.accounts.views.verify_google_token")
    def test_google_auth_disabled_account_forbidden(self, mock_verify):
        """Disabled account returns 403 Forbidden."""
        UserAccount.objects.create_user(
            email="disabled@example.com",
            password="Password123!",
            is_active=False,
        )

        mock_verify.return_value = {
            "sub": "google-uid-disabled",
            "email": "disabled@example.com",
            "first_name": "Disabled",
            "last_name": "Account",
            "full_name": "Disabled Account",
            "picture": "",
        }

        resp = self.client.post(
            "/api/auth/google/",
            data={"id_token": "some-token"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)


