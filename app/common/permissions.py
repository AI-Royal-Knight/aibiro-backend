from typing import Iterable, Sequence, Type
from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView

from app.accounts.models import UserAccount


class IsSuperAdmin(permissions.BasePermission):
    """
    Allows access only to Super Admins (or Django superusers).
    """

    message = "Super Admin privileges are required to perform this action."

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_super_admin)


class IsAdmin(permissions.BasePermission):
    """
    Allows access to Super Admins and Admins.
    """

    message = "Administrator privileges are required to perform this action."

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_admin_user)


class IsStaff(permissions.BasePermission):
    """
    Allows access to Super Admins, Admins, and Staff members.
    """

    message = "Staff privileges are required to perform this action."

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_staff_member)


class IsQAReviewer(permissions.BasePermission):
    """
    Allows access to QA Reviewers (and administrative supervisors).
    """

    message = "QA Reviewer privileges are required to perform this action."

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_qa_reviewer)


class IsClient(permissions.BasePermission):
    """
    Allows access strictly to Clients.
    """

    message = "Client account is required to perform this action."

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_client)


class RolePermission(permissions.BasePermission):
    """
    View-level permission class inspecting `allowed_roles` on the view.

    Example:
        class DocumentReviewView(APIView):
            permission_classes = [RolePermission]
            allowed_roles = [UserAccount.Role.QA_REVIEWER, UserAccount.Role.ADMIN]
    """

    message = "You do not have the required role to access this resource."

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False

        if user.is_super_admin:
            return True

        allowed_roles = getattr(view, "allowed_roles", None)
        if allowed_roles is None:
            return True

        return user.role in allowed_roles


def HasRole(*roles: str) -> Type[permissions.BasePermission]:
    """
    Factory function generating a DRF permission class that permits
    any user holding one of the specified roles (or superuser).

    Example:
        permission_classes = [HasRole(UserAccount.Role.ADMIN, UserAccount.Role.STAFF)]
    """

    class DynamicRolePermission(permissions.BasePermission):
        message = f"One of the following roles is required: {', '.join(roles)}."

        def has_permission(self, request: Request, view: APIView) -> bool:
            user = request.user
            return bool(user and user.is_authenticated and user.has_role(*roles))

    return DynamicRolePermission


def HasRoleOrHigher(min_role: str) -> Type[permissions.BasePermission]:
    """
    Factory function generating a DRF permission class that permits
    users at or above the given hierarchy role level.

    Hierarchy:
        SUPER_ADMIN (100) > ADMIN (80) > STAFF (60) > QA_REVIEWER (40) > CLIENT (20)

    Example:
        permission_classes = [HasRoleOrHigher(UserAccount.Role.STAFF)]
    """

    class DynamicHierarchyPermission(permissions.BasePermission):
        message = f"Role level {min_role} or higher is required."

        def has_permission(self, request: Request, view: APIView) -> bool:
            user = request.user
            return bool(user and user.is_authenticated and user.has_role_or_higher(min_role))

    return DynamicHierarchyPermission
