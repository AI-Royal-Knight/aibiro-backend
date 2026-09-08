from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView

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
from .models import UserAccount

__all__ = [
    "IsSuperAdmin",
    "IsAdmin",
    "IsStaff",
    "IsQAReviewer",
    "IsClient",
    "HasRole",
    "HasRoleOrHigher",
    "RolePermission",
    "CanManageUserRoles",
]


class CanManageUserRoles(permissions.BasePermission):
    """
    Permission allowing Super Admins and Admins to manage user accounts and assign roles.

    Rules:
    - Super Admin: Can manage any user and assign any role.
    - Admin: Can manage Staff, QA Reviewer, and Client accounts; cannot edit Super Admins
      and cannot promote users to Super Admin.
    - All other roles: Denied.
    """

    message = "You do not have permission to manage user roles."

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_admin_user)

    def has_object_permission(self, request: Request, view: APIView, obj: UserAccount) -> bool:
        user = request.user
        if not (user and user.is_authenticated and user.is_admin_user):
            return False

        # Super Admin can manage anyone
        if user.is_super_admin:
            return True

        # Admin cannot modify a Super Admin's account
        if obj.role == UserAccount.Role.SUPER_ADMIN or obj.is_superuser:
            self.message = "Admins cannot modify Super Admin accounts."
            return False

        return True
