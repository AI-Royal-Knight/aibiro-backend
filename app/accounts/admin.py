from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import OTP, PasswordChangeHistory, UserAccount


@admin.register(UserAccount)
class UserAccountAdmin(BaseUserAdmin):
    list_display = (
        "email",
        "full_name",
        "job_title",
        "phone_number",
        "role",
        "is_staff",
        "is_active",
        "date_joined",
    )
    list_filter = ("role", "auth_provider", "is_staff", "is_active")
    search_fields = ("email", "full_name", "first_name", "last_name", "job_title", "phone_number")
    ordering = ("-date_joined",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Personal Info",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "full_name",
                    "job_title",
                    "phone_number",
                    "username",
                    "profile_pic",
                )
            },
        ),
        (
            "Authentication",
            {"fields": ("auth_provider", "provider_uid")},
        ),
        (
            "Permissions & Roles",
            {
                "fields": (
                    "role",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "password"),
            },
        ),
    )


@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "is_valid")
    search_fields = ("user__email",)
    ordering = ("-created_at",)


@admin.register(PasswordChangeHistory)
class PasswordChangeHistoryAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "device_info", "location", "ip_address", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("user__email", "device_info", "location", "ip_address")
    ordering = ("-created_at",)
    readonly_fields = (
        "id",
        "user",
        "status",
        "device_info",
        "location",
        "ip_address",
        "user_agent",
        "created_at",
        "updated_at",
    )
