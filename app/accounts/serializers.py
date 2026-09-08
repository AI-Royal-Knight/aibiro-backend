from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import PasswordChangeHistory, UserAccount


class UserAccountSerializer(serializers.ModelSerializer):
    """
    Public representation of a user account.
    """

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
        )
        read_only_fields = fields


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

    full_name = serializers.CharField(
        max_length=150,
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
        if UserAccount.objects.filter(email=normalized_email).exists():
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
        user_instance = UserAccount(email=attrs.get("email"), full_name=attrs.get("full_name"))
        validate_password(password, user=user_instance)

        return attrs

    def create(self, validated_data: dict) -> UserAccount:
        validated_data.pop("confirm_password")
        password = validated_data.pop("password")
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
        required=True,
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

    def validate_current_password(self, value: str) -> str:
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password does not match.")
        return value

    def validate(self, attrs: dict) -> dict:
        current_password = attrs.get("current_password")
        new_password = attrs.get("new_password")
        confirm_new_password = attrs.get("confirm_new_password")

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

