from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import PasswordChangeHistory, UserAccount, NotificationSettings


class UserAccountSerializer(serializers.ModelSerializer):
    """
    Public representation of a user account.
    """

    has_usable_password = serializers.SerializerMethodField()

    class Meta:
        model = UserAccount
        fields = (
            "id",
            "email",
            "full_name",
            "first_name",
            "last_name",
            "username",
            "phone_number",
            "job_title",
            "profile_pic",
            "role",
            "auth_provider",
            "two_factor_enabled",
            "two_factor_method",
            "is_verified",
            "is_active",
            "date_joined",
            "created_at",
            "has_usable_password",
        )
        read_only_fields = fields

    def get_has_usable_password(self, obj) -> bool:
        return obj.has_usable_password()


class ProfileSettingsSerializer(serializers.ModelSerializer):
    """
    Serializer for updating Profile Settings matching the UI:
    First Name, Last Name, Email Address, Phone Number, Job Title, Profile Pic.
    """

    class Meta:
        model = UserAccount
        fields = (
            "first_name",
            "last_name",
            "full_name",
            "email",
            "phone_number",
            "job_title",
            "profile_pic",
        )
        read_only_fields = ("full_name",)

    def validate_email(self, value: str) -> str:
        normalized_email = value.lower().strip()
        user = self.instance
        if (
            UserAccount.objects.filter(email=normalized_email)
            .exclude(id=user.id if user else None)
            .exists()
        ):
            raise serializers.ValidationError("An account with this email address already exists.")
        return normalized_email


class SignUpSerializer(serializers.Serializer):
    """
    Serializer for user registration.
    Matches the Sign Up UI: Full Name, Email, Password, Confirm Password.
    """

    first_name = serializers.CharField(
        max_length=80,
        required=True,
        trim_whitespace=True,
    )
    last_name = serializers.CharField(
        max_length=80,
        required=True,
        trim_whitespace=True,
    )
    email = serializers.EmailField(
        required=True,
    )
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )
    confirm_password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )

    def validate_email(self, value: str) -> str:
        normalized_email = value.lower().strip()
        user = UserAccount.objects.filter(email=normalized_email).first()
        if user and user.is_verified:
            raise serializers.ValidationError("An account with this email address already exists.")
        return normalized_email

    def validate(self, attrs: dict) -> dict:
        password = attrs.get("password")
        confirm_password = attrs.get("confirm_password")

        if password != confirm_password:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )

        # Validate password strength using Django configured validators
        user_instance = UserAccount(
            email=attrs.get("email"),
            first_name=attrs.get("first_name"),
            last_name=attrs.get("last_name")
        )
        validate_password(password, user=user_instance)

        return attrs

    def create(self, validated_data: dict) -> UserAccount:
        validated_data.pop("confirm_password")
        password = validated_data.pop("password")
        email = validated_data.get("email")
        
        user = UserAccount.objects.filter(email=email).first()
        if user and not user.is_verified:
            # Update existing unverified user with new details
            user.first_name = validated_data.get("first_name", user.first_name)
            user.last_name = validated_data.get("last_name", user.last_name)
            user.set_password(password)
            user.save()
            return user
            
        user = UserAccount.objects.create_user(
            password=password,
            is_verified=False,
            **validated_data,
        )
        return user


class VerifyOTPSerializer(serializers.Serializer):
    """
    Serializer for verifying a one-time passcode.
    """

    email = serializers.EmailField(required=True)
    otp = serializers.CharField(
        required=True,
        max_length=10,
        trim_whitespace=True,
    )

    def validate_email(self, value: str) -> str:
        return value.lower().strip()

    def validate_otp(self, value: str) -> str:
        return value.strip()


class ResendOTPSerializer(serializers.Serializer):
    """
    Serializer for resending a verification code.
    """

    email = serializers.EmailField(required=True)

    def validate_email(self, value: str) -> str:
        return value.lower().strip()


class LoginSerializer(serializers.Serializer):
    """
    Serializer for authenticating with email and password.
    """

    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )

    def validate_email(self, value: str) -> str:
        return value.lower().strip()

    def validate(self, attrs: dict) -> dict:
        email = attrs.get("email")
        password = attrs.get("password")

        user = authenticate(request=self.context.get("request"), username=email, password=password)
        if not user:
            raise serializers.ValidationError("Invalid email or password.")

        if not user.is_active:
            raise serializers.ValidationError("This account is inactive. Please contact support.")

        attrs["user"] = user
        return attrs


class LogoutSerializer(serializers.Serializer):
    """
    Serializer for blacklisting the refresh token upon logout.
    """

    refresh = serializers.CharField(required=True)


class PasswordUpdateSerializer(serializers.Serializer):
    """
    Serializer for updating user password matching Security Settings UI:
    Current Password, New Password, Confirm New Password.
    """

    current_password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        style={"input_type": "password"},
    )
    new_password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )
    confirm_new_password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )

    def validate(self, attrs: dict) -> dict:
        user = self.context["request"].user
        current_password = attrs.get("current_password")
        new_password = attrs.get("new_password")
        confirm_new_password = attrs.get("confirm_new_password")

        if user.has_usable_password():
            if not current_password:
                raise serializers.ValidationError(
                    {"current_password": "This field is required when updating an existing password."}
                )
            if not user.check_password(current_password):
                raise serializers.ValidationError(
                    {"current_password": "Current password does not match."}
                )

        if new_password != confirm_new_password:
            raise serializers.ValidationError(
                {"confirm_new_password": "New passwords do not match."}
            )

        if new_password == current_password:
            raise serializers.ValidationError(
                {"new_password": "New password cannot be the same as the current password."}
            )

        user = self.context["request"].user
        validate_password(new_password, user=user)

        return attrs

    def save(self, **kwargs) -> UserAccount:
        user = self.context["request"].user
        new_password = self.validated_data["new_password"]
        user.set_password(new_password)
        user.save()
        return user


class TwoFactorToggleSerializer(serializers.Serializer):
    """
    Serializer for enabling or disabling Two-Factor Authentication.
    """

    enable = serializers.BooleanField(required=True)
    method = serializers.ChoiceField(
        choices=UserAccount.TwoFactorMethod.choices,
        required=False,
        default=UserAccount.TwoFactorMethod.EMAIL,
    )


class NotificationSettingsSerializer(serializers.ModelSerializer):
    """
    Serializer for NotificationSettings.
    """

    class Meta:
        model = NotificationSettings
        fields = (
            "email_notifications",
            "project_updates",
            "payment_reminders",
            "ai_analysis_reports",
            "critical_alerts",
            "weekly_summary",
        )


class PasswordChangeHistorySerializer(serializers.ModelSerializer):
    """
    Serializer for listing user password change audit events,
    matching the Password Change History UI.
    """

    formatted_date = serializers.SerializerMethodField()
    device_summary = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = PasswordChangeHistory
        fields = (
            "id",
            "created_at",
            "formatted_date",
            "device_info",
            "location",
            "device_summary",
            "ip_address",
            "status",
            "status_display",
        )
        read_only_fields = fields

    def get_formatted_date(self, obj) -> str:
        """e.g. 'Oct 12, 2026, 14:30' matching the UI mockup."""
        return obj.created_at.strftime("%b %d, %Y, %H:%M")

    def get_device_summary(self, obj) -> str:
        """e.g. 'MacBook Pro (Mac OS) • Lisbon, Portugal' matching the UI."""
        parts = [p for p in [obj.device_info, obj.location] if p]
        return " • ".join(parts)


class UserManagementSerializer(serializers.ModelSerializer):
    """
    Representation of a user account for administrator user management and auditing.
    """

    role_display = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = UserAccount
        fields = (
            "id",
            "email",
            "full_name",
            "first_name",
            "last_name",
            "username",
            "role",
            "role_display",
            "auth_provider",
            "is_active",
            "is_staff",
            "is_superuser",
            "is_verified",
            "date_joined",
            "last_login",
        )
        read_only_fields = fields


class UpdateUserRoleSerializer(serializers.Serializer):
    """
    Serializer for updating a user's role by an authorized administrator.
    """

    role = serializers.ChoiceField(
        choices=UserAccount.Role.choices,
        required=True,
    )

    def validate_role(self, value: str) -> str:
        request = self.context.get("request")
        target_user = self.context.get("target_user")

        if request and request.user:
            # Only Super Admins can assign the SUPER_ADMIN role
            if value == UserAccount.Role.SUPER_ADMIN and not request.user.is_super_admin:
                raise serializers.ValidationError(
                    "Only Super Admins can assign the Super Admin role."
                )

            # Admins cannot modify Super Admin accounts
            if target_user and (target_user.role == UserAccount.Role.SUPER_ADMIN or target_user.is_superuser):
                if not request.user.is_super_admin:
                    raise serializers.ValidationError(
                        "Only Super Admins can modify Super Admin accounts."
                    )

        return value


class GoogleAuthSerializer(serializers.Serializer):
    """
    Serializer for Google OAuth authentication payload.
    Accepts either an ID token or an OAuth access token.
    """

    id_token = serializers.CharField(required=False, allow_blank=True)
    access_token = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        id_token = attrs.get("id_token")
        access_token = attrs.get("access_token")
        if not id_token and not access_token:
            raise serializers.ValidationError(
                "Either id_token or access_token must be provided."
            )
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    """
    Serializer to request a password reset via email.
    """
    email = serializers.EmailField()


class PasswordResetVerifySerializer(serializers.Serializer):
    """
    Serializer to verify OTP and set a new password.
    """
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=10)
    new_password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )
    confirm_new_password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )

    def validate(self, attrs: dict) -> dict:
        new_password = attrs.get("new_password")
        confirm_new_password = attrs.get("confirm_new_password")

        if new_password != confirm_new_password:
            raise serializers.ValidationError(
                {"confirm_new_password": "New passwords do not match."}
            )

        validate_password(new_password)
        return attrs


class UserInviteSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate_email(self, value):
        from .models import UserAccount
        if UserAccount.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.lower().strip()


class AcceptInvitationSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(min_length=8)

    def validate_new_password(self, value):
        from django.contrib.auth.password_validation import validate_password
        validate_password(value)
        return value
