from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView

from app.accounts.models import UserAccount
from .models import Project, Document


class IsProjectOwnerOrAdmin(permissions.BasePermission):
    """
    Project-level permission:
    - Super Admins and Admins: Full access to all projects and attached files.
    - Staff & QA Reviewers: Read-only access to all projects and documents for review.
    - Clients: Full access (create, read, update, upload files, delete) strictly to their OWN projects.
    - Other users / unauthenticated: Access denied.
    """

    message = "You do not have permission to access or modify this project."

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False

        # Super Admin and Admin have full unrestricted access
        if user.is_admin_user:
            return True

        # Resolve target project
        project = obj if isinstance(obj, Project) else getattr(obj, "project", None)
        if not project:
            return False

        # Staff and QA Reviewers have read-only review access
        if user.role in (UserAccount.Role.STAFF, UserAccount.Role.QA_REVIEWER):
            return request.method in permissions.SAFE_METHODS

        # Project owner (Client) has full access to their project
        return project.owner_id == user.id
