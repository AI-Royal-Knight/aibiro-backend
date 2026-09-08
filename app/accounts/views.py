from django.db import models
from rest_framework import generics, serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import PasswordChangeHistory, UserAccount
from .serializers import (
    LoginSerializer,
    LogoutSerializer,
    PasswordChangeHistorySerializer,
    PasswordUpdateSerializer,
    ProfileSettingsSerializer,
    ResendOTPSerializer,
    SignUpSerializer,
    TwoFactorToggleSerializer,
    UpdateUserRoleSerializer,
    UserAccountSerializer,
    UserManagementSerializer,
    VerifyOTPSerializer,
)
from .permissions import CanManageUserRoles, IsAdmin
from .utils import (
    create_otp_for_user,
    record_password_change_event,
    send_otp_email,
    verify_otp_for_user,
)


def get_tokens_for_user(user: UserAccount) -> dict:
    """Generate JWT access and refresh token pair for user with role claim."""
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role
    refresh.access_token["role"] = user.role
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


class SignUpView(APIView):
    """
    Class-based view for user account creation.
    Creates a new user and sends an OTP verification code to their email.
    """

    permission_classes = [AllowAny]
    serializer_class = SignUpSerializer

    def post(self, request: Request) -> Response:
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.save()

        # Generate and dispatch OTP
        _, raw_otp = create_otp_for_user(user)
        send_otp_email(user, raw_otp)

        return Response(
            {
                "success": True,
                "message": "Account created successfully. A 6-digit verification code has been sent to your email.",
                "data": UserAccountSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class VerifyOTPView(APIView):
    """
    Class-based view for OTP code verification.
    Verifies the email, marks the user verified, and issues JWT tokens.
    """

    permission_classes = [AllowAny]
    serializer_class = VerifyOTPSerializer

    def post(self, request: Request) -> Response:
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        raw_otp = serializer.validated_data["otp"]

        user = UserAccount.objects.filter(email=email).first()
        if not user:
            return Response(
                {"success": False, "message": "No account found with this email address."},
                status=status.HTTP_404_NOT_FOUND,
            )

        is_valid, error_msg = verify_otp_for_user(user, raw_otp)
        if not is_valid:
            return Response(
                {"success": False, "message": error_msg},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Issue JWT tokens upon successful verification
        tokens = get_tokens_for_user(user)

        return Response(
            {
                "success": True,
                "message": "Email verified successfully.",
                "tokens": tokens,
                "user": UserAccountSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


class ResendOTPView(APIView):
    """
    Class-based view to resend a verification code.
    """

    permission_classes = [AllowAny]
    serializer_class = ResendOTPSerializer

    def post(self, request: Request) -> Response:
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        user = UserAccount.objects.filter(email=email).first()

        if not user:
            # Generic response to prevent email enumeration
            return Response(
                {
                    "success": True,
                    "message": "If an account exists with this email, a new verification code has been sent.",
                },
                status=status.HTTP_200_OK,
            )

        if user.is_verified:
            return Response(
                {
                    "success": True,
                    "message": "This account is already verified. You can log in directly.",
                },
                status=status.HTTP_200_OK,
            )

        _, raw_otp = create_otp_for_user(user)
        send_otp_email(user, raw_otp)

        return Response(
            {
                "success": True,
                "message": "A new verification code has been sent to your email.",
            },
            status=status.HTTP_200_OK,
        )


class LoginView(APIView):
    """
    Class-based view for user authentication via email & password.
    Returns JWT tokens on successful authentication.
    """

    permission_classes = [AllowAny]
    serializer_class = LoginSerializer

    def post(self, request: Request) -> Response:
        serializer = self.serializer_class(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        user: UserAccount = serializer.validated_data["user"]

        # If Two-Factor Authentication is enabled, dispatch OTP challenge
        if user.two_factor_enabled:
            _, raw_otp = create_otp_for_user(user)
            send_otp_email(user, raw_otp)
            return Response(
                {
                    "success": True,
                    "two_factor_required": True,
                    "message": "Two-factor authentication is required. A verification code has been sent to your email.",
                    "email": user.email,
                },
                status=status.HTTP_200_OK,
            )

        tokens = get_tokens_for_user(user)

        return Response(
            {
                "success": True,
                "message": "Login successful.",
                "tokens": tokens,
                "user": UserAccountSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    """
    Class-based view to logout by blacklisting the refresh token.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = LogoutSerializer

    def post(self, request: Request) -> Response:
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        refresh_token = serializer.validated_data["refresh"]

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(
                {"success": True, "message": "Logged out successfully."},
                status=status.HTTP_200_OK,
            )
        except Exception:
            return Response(
                {"success": False, "message": "Invalid or already blacklisted token."},
                status=status.HTTP_400_BAD_REQUEST,
            )


class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    Class-based view to retrieve and update the authenticated user's profile settings:
    First Name, Last Name, Email, Phone Number, Job Title, Profile Pic.
    """

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method in ["PUT", "PATCH"]:
            return ProfileSettingsSerializer
        return UserAccountSerializer

    def get_object(self) -> UserAccount:
        return self.request.user

    def update(self, request: Request, *args, **kwargs) -> Response:
        partial = kwargs.pop("partial", True)  # Support partial PATCH by default
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(
            {
                "success": True,
                "message": "Profile settings updated successfully.",
                "user": UserAccountSerializer(instance).data,
            },
            status=status.HTTP_200_OK,
        )


class PasswordUpdateView(APIView):
    """
    Class-based view for updating user password matching Security Settings UI:
    Current Password, New Password, Confirm New Password.
    Also records an audit log entry in PasswordChangeHistory (success/failed).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = PasswordUpdateSerializer

    def post(self, request: Request) -> Response:
        serializer = self.serializer_class(data=request.data, context={"request": request})
        try:
            serializer.is_valid(raise_exception=True)
        except serializers.ValidationError:
            record_password_change_event(
                request=request,
                user=request.user,
                status=PasswordChangeHistory.Status.FAILED,
            )
            raise

        serializer.save()
        record_password_change_event(
            request=request,
            user=request.user,
            status=PasswordChangeHistory.Status.SUCCESS,
        )

        return Response(
            {
                "success": True,
                "message": "Password updated successfully.",
            },
            status=status.HTTP_200_OK,
        )


class PasswordChangeHistoryView(generics.ListAPIView):
    """
    Class-based view to list password change history and security events for the authenticated user.
    Matches the 'Password Change History' UI.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = PasswordChangeHistorySerializer

    def get_queryset(self):
        return PasswordChangeHistory.objects.filter(user=self.request.user).order_by("-created_at")


class TwoFactorToggleView(APIView):
    """
    Class-based view to enable or disable Two-Factor Authentication (2FA).
    Matches the Two-Factor Authentication toggle in Security Settings UI.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = TwoFactorToggleSerializer

    def get(self, request: Request) -> Response:
        user = request.user
        return Response(
            {
                "success": True,
                "two_factor_enabled": user.two_factor_enabled,
                "two_factor_method": user.two_factor_method,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request: Request) -> Response:
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        enable = serializer.validated_data["enable"]
        method = serializer.validated_data.get("method", UserAccount.TwoFactorMethod.EMAIL)

        user = request.user
        user.two_factor_enabled = enable
        if enable:
            user.two_factor_method = method
        user.save(update_fields=["two_factor_enabled", "two_factor_method"])

        action_word = "enabled" if enable else "disabled"
        return Response(
            {
                "success": True,
                "message": f"Two-factor authentication has been {action_word} successfully.",
                "data": {
                    "two_factor_enabled": user.two_factor_enabled,
                    "two_factor_method": user.two_factor_method,
                },
            },
            status=status.HTTP_200_OK,
        )


class UserManagementListView(generics.ListAPIView):
    """
    List user accounts with optional filtering by role and search keyword.
    Restricted to Admins and Super Admins.
    """

    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = UserManagementSerializer

    def get_queryset(self):
        queryset = UserAccount.objects.all().order_by("-date_joined")
        role = self.request.query_params.get("role")
        search = self.request.query_params.get("search")

        if role:
            queryset = queryset.filter(role=role.lower().strip())

        if search:
            search = search.strip()
            queryset = queryset.filter(
                models.Q(email__icontains=search)
                | models.Q(full_name__icontains=search)
                | models.Q(username__icontains=search)
                | models.Q(phone_number__icontains=search)
            )

        return queryset


class UserRoleUpdateView(APIView):
    """
    Update a user's role.
    Restricted to Admins and Super Admins via CanManageUserRoles.
    """

    permission_classes = [IsAuthenticated, CanManageUserRoles]
    serializer_class = UpdateUserRoleSerializer

    def patch(self, request: Request, pk) -> Response:
        try:
            target_user = UserAccount.objects.get(pk=pk)
        except (UserAccount.DoesNotExist, ValueError):
            return Response(
                {"detail": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        self.check_object_permissions(request, target_user)

        serializer = self.serializer_class(
            data=request.data,
            context={"request": request, "target_user": target_user},
        )
        serializer.is_valid(raise_exception=True)

        new_role = serializer.validated_data["role"]
        target_user.role = new_role
        target_user.save(update_fields=["role", "updated_at"])

        return Response(
            {
                "success": True,
                "message": f"User role successfully updated to {target_user.get_role_display()}.",
                "data": UserManagementSerializer(target_user).data,
            },
            status=status.HTTP_200_OK,
        )

