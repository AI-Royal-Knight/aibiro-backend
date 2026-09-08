from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    LoginView,
    LogoutView,
    PasswordChangeHistoryView,
    PasswordUpdateView,
    ResendOTPView,
    SignUpView,
    TwoFactorToggleView,
    UserManagementListView,
    UserProfileView,
    UserRoleUpdateView,
    VerifyOTPView,
)

urlpatterns = [
    path("register/", SignUpView.as_view(), name="register"),
    path("signup/", SignUpView.as_view(), name="signup"),
    path("verify-otp/", VerifyOTPView.as_view(), name="verify-otp"),
    path("resend-otp/", ResendOTPView.as_view(), name="resend-otp"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("profile/", UserProfileView.as_view(), name="profile"),
    path("profile/settings/", UserProfileView.as_view(), name="profile-settings"),
    path("security/password/", PasswordUpdateView.as_view(), name="password-update"),
    path("security/password-history/", PasswordChangeHistoryView.as_view(), name="password-history"),
    path("security/password/history/", PasswordChangeHistoryView.as_view(), name="password-history-alias"),
    path("security/2fa/", TwoFactorToggleView.as_view(), name="2fa-toggle"),
    path("users/", UserManagementListView.as_view(), name="user-list"),
    path("users/<uuid:pk>/role/", UserRoleUpdateView.as_view(), name="user-role-update"),
]
