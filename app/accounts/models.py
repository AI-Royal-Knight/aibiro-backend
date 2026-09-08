from datetime import timedelta

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from cloudinary.models import CloudinaryField

from app.common.models import BaseModel


class CustomAccountManager(BaseUserManager):
    """
    Custom manager where email is the unique identifier for authentication.
    """

    def normalize_email_strict(self, email: str) -> str:
        return self.normalize_email(email).lower().strip()

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_("Email must be provided"))

        email = self.normalize_email_strict(email)
        user = self.model(email=email, **extra_fields)

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("role", UserAccount.Role.SUPER_ADMIN)

        if not extra_fields.get("is_staff"):
            raise ValueError("Superuser must have is_staff=True")
        if not extra_fields.get("is_superuser"):
            raise ValueError("Superuser must have is_superuser=True")

        return self.create_user(email, password, **extra_fields)


class UserAccount(AbstractBaseUser, PermissionsMixin, BaseModel):
    """
    Minimal custom user model for Aibiro:
    - UUID primary key, created_at, updated_at (inherited from BaseModel)
    - Email-based authentication
    - Support for standard credentials and Google OAuth
    """

    class AuthProvider(models.TextChoices):
        EMAIL = "email", "Email"
        GOOGLE = "google", "Google"

    class Role(models.TextChoices):
        SUPER_ADMIN = "super_admin", _("Super Admin")
        ADMIN = "admin", _("Admin")
        STAFF = "staff", _("Staff")
        QA_REVIEWER = "qa_reviewer", _("QA Reviewer")
        CLIENT = "client", _("Client")

    # Backward compatibility alias
    Role.USER = Role.CLIENT

    ROLE_HIERARCHY = {
        Role.SUPER_ADMIN: 100,
        Role.ADMIN: 80,
        Role.STAFF: 60,
        Role.QA_REVIEWER: 40,
        Role.CLIENT: 20,
    }

    groups = models.ManyToManyField(
        "auth.Group",
        blank=True,
        related_name="account_set",
        related_query_name="account",
        verbose_name="groups",
    )
    user_permissions = models.ManyToManyField(
        "auth.Permission",
        blank=True,
        related_name="account_set",
        related_query_name="account",
        verbose_name="user permissions",
    )

    email = models.EmailField(
        _("email address"),
        unique=True,
    )
    full_name = models.CharField(max_length=150, blank=True)
    first_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80, blank=True)
    username = models.CharField(max_length=50, unique=True, blank=True)

    phone_number = models.CharField(max_length=30, blank=True, null=True)
    job_title = models.CharField(max_length=100, blank=True, null=True)
    profile_pic = CloudinaryField(blank=True, null=True)

    auth_provider = models.CharField(
        max_length=20,
        choices=AuthProvider.choices,
        default=AuthProvider.EMAIL,
    )
    provider_uid = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CLIENT,
    )

    class TwoFactorMethod(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"
        BOTH = "both", "Email + SMS"

    two_factor_enabled = models.BooleanField(default=False)
    two_factor_method = models.CharField(
        max_length=10,
        choices=TwoFactorMethod.choices,
        default=TwoFactorMethod.EMAIL,
        blank=True,
        null=True,
    )

    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = CustomAccountManager()

    class Meta:
        verbose_name = "User Account"
        verbose_name_plural = "User Accounts"
        ordering = ["-date_joined"]
        indexes = [
            models.Index(fields=["username"]),
            models.Index(fields=["provider_uid"]),
            models.Index(fields=["date_joined"]),
        ]

    def clean(self):
        if self.auth_provider != self.AuthProvider.EMAIL and not self.provider_uid:
            raise ValidationError("OAuth users must provide provider_uid.")

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.lower().strip()

        # Synchronize first_name, last_name, and full_name
        if self.first_name or self.last_name:
            self.full_name = f"{self.first_name} {self.last_name}".strip()
        elif self.full_name and not self.first_name and not self.last_name:
            parts = self.full_name.strip().split(" ", 1)
            self.first_name = parts[0]
            if len(parts) > 1:
                self.last_name = parts[1]

        # Generate unique username from email if not set
        if not self.username and self.email:
            base_username = self.email.split("@")[0]
            base_username = "".join(c for c in base_username if c.isalnum() or c in "._-")[:40]
            if not base_username:
                base_username = "user"

            username = base_username
            counter = 1
            while UserAccount.objects.filter(username=username).exclude(id=self.id).exists():
                suffix = str(counter)
                username = f"{base_username[:50 - len(suffix)]}{suffix}"
                counter += 1

            self.username = username

        super().save(*args, **kwargs)

    def __str__(self):
        return self.email

    @property
    def is_super_admin(self) -> bool:
        return self.is_superuser or self.role == self.Role.SUPER_ADMIN

    @property
    def is_admin_user(self) -> bool:
        return self.is_super_admin or self.role == self.Role.ADMIN

    @property
    def is_staff_member(self) -> bool:
        return self.is_admin_user or self.role == self.Role.STAFF

    @property
    def is_qa_reviewer(self) -> bool:
        return self.is_admin_user or self.role == self.Role.QA_REVIEWER

    @property
    def is_client(self) -> bool:
        return self.role == self.Role.CLIENT

    def has_role(self, *roles: str) -> bool:
        """Check whether the user matches any of the given roles, or is a superuser/super admin."""
        if self.is_super_admin:
            return True
        return self.role in roles

    def has_role_or_higher(self, min_role: str) -> bool:
        """Check if user's role hierarchy level is >= min_role hierarchy level."""
        if self.is_super_admin:
            return True
        user_weight = self.ROLE_HIERARCHY.get(self.role, 0)
        target_weight = self.ROLE_HIERARCHY.get(min_role, 0)
        return user_weight >= target_weight


class OTP(BaseModel):
    """
    Minimal one-time code for email verification or password reset.
    """

    user = models.ForeignKey(
        UserAccount,
        on_delete=models.CASCADE,
        related_name="otps",
    )
    otp_hash = models.CharField(max_length=128)
    is_used = models.BooleanField(default=False)

    class Meta:
        verbose_name = "OTP"
        verbose_name_plural = "OTPs"
        indexes = [
            models.Index(fields=["created_at"]),
        ]

    def is_valid(self, expiry_minutes=5):
        if self.is_used:
            return False
        expiry_time = self.created_at + timedelta(minutes=expiry_minutes)
        return timezone.now() <= expiry_time

    def is_expired(self, expiry_minutes=5):
        return not self.is_valid(expiry_minutes)

    def __str__(self):
        return f"OTP for {self.user.email}"


class PasswordChangeHistory(BaseModel):
    """
    Audit log of password change attempts and security events.
    Tracks timestamp, device, location, IP address, and success/failure status.
    """

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed Attempt"

    user = models.ForeignKey(
        UserAccount,
        on_delete=models.CASCADE,
        related_name="password_changes",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SUCCESS,
    )
    device_info = models.CharField(
        max_length=150,
        blank=True,
        default="Unknown Device",
        help_text="e.g. MacBook Pro (Mac OS)",
    )
    location = models.CharField(
        max_length=150,
        blank=True,
        default="Unknown Location",
        help_text="e.g. Lisbon, Portugal",
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
    )
    user_agent = models.TextField(blank=True)

    class Meta:
        verbose_name = "Password Change History"
        verbose_name_plural = "Password Change Histories"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} - {self.status} at {self.created_at}"
