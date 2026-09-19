from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView

from app.accounts.models import UserAccount
from .models import Project, Document


class IsAdminOnly(permissions.BasePermission):
    """
    Strictly restricts permission to Admins and Super Admins.
    Used for creating projects from service workflows and managing organizational templates.
    """

    message = "Only administrators have permission to perform this action."

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "is_admin_user", False)
        )


class IsProjectOwnerOrAdmin(permissions.BasePermission):
    """
    Project-level permission:
    - Super Admins and Admins: Full access to all projects and attached files.
    - Staff: Access to projects where they are assigned (via ProjectStaffAssignment or assigned tasks).
    - QA Reviewers: Access to projects where tasks require review.
    - Clients: Read/write access strictly to their OWN projects.
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

        # Staff can view projects where they are assigned to a role or task
        if user.role == UserAccount.Role.STAFF:
            is_assigned = (
                project.staff_assignments.filter(staff=user).exists()
                or project.tasks.filter(assigned_to=user).exists()
            )
            return is_assigned

        # QA Reviewers can view for audit and review purposes
        if user.role == UserAccount.Role.QA_REVIEWER:
            return True

        # Project owner (Client) has access to their project
        return project.owner_id == user.id


class IsTaskAssigneeOrAdmin(permissions.BasePermission):
    """
    Permits task updates if user is the assigned staff member or an administrator.
    """

    message = "You can only update tasks assigned to you."

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_admin_user:
            return True
        return obj.assigned_to_id == user.id


class IsQAReviewerOrAdmin(permissions.BasePermission):
    """
    Restricts QA review actions (approve/request changes) to QA Reviewers and Admins.
    """

    message = "Only designated QA Reviewers or Administrators can review submissions."

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.is_admin_user or user.role == UserAccount.Role.QA_REVIEWER)
        )
