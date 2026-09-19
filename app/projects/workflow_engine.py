import datetime
from typing import Any, Dict, List, Optional
from django.db.models import Count, Q
from django.utils import timezone

from app.accounts.models import UserAccount
from .models import (
    Project,
    ProjectPhase,
    ProjectTask,
    ProjectStaffAssignment,
    ServiceWorkflowTemplate,
)


def get_active_staff_with_workload() -> List[Dict[str, Any]]:
    """
    Returns all active Staff and Admin users annotated with their active task counts.
    """
    candidates = (
        UserAccount.objects.filter(
            is_active=True,
            role__in=[UserAccount.Role.STAFF, UserAccount.Role.ADMIN, UserAccount.Role.SUPER_ADMIN],
        )
        .annotate(
            active_tasks_count=Count(
                "assigned_project_tasks",
                filter=Q(assigned_project_tasks__status__in=[
                    ProjectTask.TaskStatus.TODO,
                    ProjectTask.TaskStatus.IN_PROGRESS,
                    ProjectTask.TaskStatus.SUBMITTED_FOR_QA,
                ]),
            )
        )
        .order_by("active_tasks_count", "email")
    )

    staff_list = []
    for c in candidates:
        name = c.full_name or f"{c.first_name} {c.last_name}".strip() or c.username or c.email.split("@")[0]
        staff_list.append({
            "id": str(c.id),
            "email": c.email,
            "name": name,
            "role": c.role,
            "job_title": c.job_title or "",
            "functional_roles": c.functional_roles or [],
            "active_tasks_count": c.active_tasks_count,
        })
    return staff_list


def auto_assign_staff_for_roles(required_roles: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    For each required functional role, select the staff member who possesses that role
    (or matching specialty domain) and has the lowest current active task workload.
    """
    available_staff = get_active_staff_with_workload()
    assignments: Dict[str, Dict[str, Any]] = {}

    for req_role in required_roles:
        req_norm = req_role.lower().strip()
        matching = []

        # 1. Look for direct match or substring
        for s in available_staff:
            staff_roles = [r.lower().strip() for r in s.get("functional_roles", [])]
            staff_title = (s.get("job_title") or "").lower().strip()

            direct_matched = any(
                r == req_norm or r in req_norm or req_norm in r
                for r in staff_roles
            )
            if not direct_matched and staff_title:
                direct_matched = staff_title in req_norm or req_norm in staff_title

            # 2. Semantic specialty domain matching based on AccrediSure consulting delivery model
            if not direct_matched:
                if any(term in req_norm for term in ["engagement lead", "strategist", "discovery"]):
                    direct_matched = any("lead" in r or "admin" in r or "project manager" in r for r in staff_roles)
                elif any(term in req_norm for term in ["compliance architect", "regulatory architect", "regulatory compliance", "licensing authority"]):
                    direct_matched = any("architect" in r or "compliance" in r for r in staff_roles)
                elif any(term in req_norm for term in ["policy specialist", "documentation specialist", "policy & documentation", "hr policy"]):
                    direct_matched = any("policy" in r or "documentation" in r for r in staff_roles)
                elif any(term in req_norm for term in ["clinical operations", "clinical consultant", "clinical", "chart review"]):
                    direct_matched = any("clinical" in r for r in staff_roles)
                elif any(term in req_norm for term in ["quality specialist", "pi specialist", "performance improvement", "qa"]):
                    direct_matched = any("quality" in r or "pi" in r for r in staff_roles)
                elif any(term in req_norm for term in ["compliance analyst", "data analyst", "data specialist", "analyst"]):
                    direct_matched = any("analyst" in r or "data" in r for r in staff_roles)
                elif any(term in req_norm for term in ["project manager", "implementation manager"]):
                    direct_matched = any("manager" in r or "lead" in r for r in staff_roles)
                elif any(term in req_norm for term in ["operations consultant", "operations architect", "operations specialist"]):
                    direct_matched = any("operations" in r or "compliance" in r or "consultant" in r for r in staff_roles)
                elif any(term in req_norm for term in ["risk specialist", "risk management"]):
                    direct_matched = any("risk" in r or "compliance" in r or "quality" in r for r in staff_roles)
                elif any(term in req_norm for term in ["licensing specialist", "credentialing specialist", "revenue"]):
                    direct_matched = any("licensing" in r or "credential" in r or "analyst" in r or "compliance" in r for r in staff_roles)

            if direct_matched:
                matching.append(s)

        if matching:
            # Sort by least active tasks, then email
            matching.sort(key=lambda x: (x["active_tasks_count"], x["email"]))
            selected = matching[0]
        elif available_staff:
            # Fallback to least loaded staff member
            selected = available_staff[0]
        else:
            selected = None

        assignments[req_role] = selected

    return assignments


def generate_workflow_preview(
    service_template: ServiceWorkflowTemplate,
    start_date: datetime.date,
    custom_project_name: Optional[str] = None,
    client_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Simulate the complete project workflow: phases, tasks, calculated dates,
    and auto-assigned staff based on workload.
    """
    duration_weeks = service_template.duration_weeks or 12
    end_date = start_date + datetime.timedelta(weeks=duration_weeks)

    # Collect distinct functional roles needed across all task templates
    phase_templates = service_template.phase_templates.prefetch_related("task_templates").all()
    required_roles_set = set()
    for pt in phase_templates:
        if pt.responsible_role:
            required_roles_set.add(pt.responsible_role)
        for tt in pt.task_templates.all():
            if tt.responsible_role:
                required_roles_set.add(tt.responsible_role)

    role_assignments = auto_assign_staff_for_roles(list(required_roles_set))

    # Build simulated phases and tasks
    simulated_phases = []
    for pt in phase_templates:
        p_start = start_date + datetime.timedelta(weeks=max(0, pt.week_start - 1))
        p_end = start_date + datetime.timedelta(weeks=pt.week_end, days=-1)
        phase_lead = role_assignments.get(pt.responsible_role)

        tasks_list = []
        for tt in pt.task_templates.all():
            t_due = start_date + datetime.timedelta(weeks=tt.relative_due_week, days=-1)
            t_assigned = role_assignments.get(tt.responsible_role)
            tasks_list.append({
                "template_id": str(tt.id),
                "title": tt.title,
                "responsible_role": tt.responsible_role,
                "assigned_to": t_assigned,
                "due_date": t_due.isoformat(),
                "deliverables": tt.deliverables or [],
                "order": tt.order,
            })

        simulated_phases.append({
            "template_id": str(pt.id),
            "phase_number": pt.phase_number,
            "name": pt.name,
            "objective": pt.objective,
            "responsible_role": pt.responsible_role,
            "lead_staff": phase_lead,
            "start_date": p_start.isoformat(),
            "end_date": p_end.isoformat(),
            "tasks": tasks_list,
        })

    generated_name = custom_project_name or f"{service_template.name}"
    if client_name and not custom_project_name:
        generated_name = f"{client_name} - {service_template.name}"

    return {
        "service_slug": service_template.slug,
        "service_name": service_template.name,
        "category_label": service_template.category_label,
        "project_name": generated_name,
        "duration_weeks": duration_weeks,
        "start_date": start_date.isoformat(),
        "target_end_date": end_date.isoformat(),
        "role_assignments": role_assignments,
        "phases": simulated_phases,
        "all_available_staff": get_active_staff_with_workload(),
    }


def create_project_from_workflow(
    client_user: UserAccount,
    service_template: ServiceWorkflowTemplate,
    start_date: datetime.date,
    company_name: str,
    project_name: Optional[str] = None,
    description: str = "",
    staff_overrides: Optional[Dict[str, str]] = None,
    custom_tasks: Optional[List[Dict[str, Any]]] = None,
    created_by_admin: Optional[UserAccount] = None,
) -> Project:
    """
    Instantiates a Project, along with its ProjectPhases, ProjectTasks,
    and ProjectStaffAssignments.
    """
    staff_overrides = staff_overrides or {}
    custom_tasks = custom_tasks or []

    duration_weeks = service_template.duration_weeks or 12
    target_end_date = start_date + datetime.timedelta(weeks=duration_weeks)

    final_name = project_name or f"{company_name} - {service_template.name}"

    # 1. Create Project
    project = Project.objects.create(
        owner=client_user,
        service_template=service_template,
        name=final_name,
        company_name=company_name,
        status=Project.ProjectStatus.ACTIVE,
        description=description or service_template.description,
        start_date=start_date,
        target_end_date=target_end_date,
        compliance_score=0,
    )

    # 2. Compute staff assignments by role
    phase_templates = service_template.phase_templates.prefetch_related("task_templates").all()
    required_roles_set = set()
    for pt in phase_templates:
        if pt.responsible_role:
            required_roles_set.add(pt.responsible_role)
        for tt in pt.task_templates.all():
            if tt.responsible_role:
                required_roles_set.add(tt.responsible_role)

    auto_assignments = auto_assign_staff_for_roles(list(required_roles_set))

    # Resolve effective staff for each role
    resolved_staff_by_role: Dict[str, Optional[UserAccount]] = {}
    for role_name in required_roles_set:
        # Check if admin explicitly overrode this role with a specific user ID
        override_user_id = staff_overrides.get(role_name)
        if override_user_id:
            user = UserAccount.objects.filter(id=override_user_id, is_active=True).first()
            if user:
                resolved_staff_by_role[role_name] = user
                continue

        # Fallback to auto-assigned user
        auto_user_dict = auto_assignments.get(role_name)
        if auto_user_dict:
            user = UserAccount.objects.filter(id=auto_user_dict["id"]).first()
            resolved_staff_by_role[role_name] = user
        else:
            resolved_staff_by_role[role_name] = created_by_admin

    # 3. Create ProjectStaffAssignment records
    for role_name, staff_obj in resolved_staff_by_role.items():
        if staff_obj:
            ProjectStaffAssignment.objects.get_or_create(
                project=project,
                staff=staff_obj,
                role_assigned=role_name,
                defaults={"is_lead": (role_name.lower() == "engagement lead")},
            )

    # 4. Create ProjectPhase and ProjectTask records
    first_phase = None
    for pt in phase_templates:
        p_start = start_date + datetime.timedelta(weeks=max(0, pt.week_start - 1))
        p_end = start_date + datetime.timedelta(weeks=pt.week_end, days=-1)

        phase_obj = ProjectPhase.objects.create(
            project=project,
            phase_template=pt,
            phase_number=pt.phase_number,
            name=pt.name,
            objective=pt.objective,
            start_date=p_start,
            end_date=p_end,
            status=ProjectPhase.PhaseStatus.IN_PROGRESS if pt.phase_number == 1 else ProjectPhase.PhaseStatus.PENDING,
        )

        if not first_phase:
            first_phase = phase_obj

        for tt in pt.task_templates.all():
            t_due = start_date + datetime.timedelta(weeks=tt.relative_due_week, days=-1)
            t_staff = resolved_staff_by_role.get(tt.responsible_role)

            ProjectTask.objects.create(
                project=project,
                phase=phase_obj,
                task_template=tt,
                title=tt.title,
                responsible_role=tt.responsible_role,
                assigned_to=t_staff,
                due_date=t_due,
                deliverables=tt.deliverables or [],
                status=ProjectTask.TaskStatus.TODO,
                priority="High" if pt.phase_number == 1 else "Medium",
                order=tt.order,
                is_custom=False,
            )

    # 5. Insert any custom tasks specified by the Admin
    if custom_tasks and first_phase:
        for idx, ct in enumerate(custom_tasks, start=100):
            assigned_user = None
            if ct.get("assigned_to_id"):
                assigned_user = UserAccount.objects.filter(id=ct["assigned_to_id"]).first()

            due_date = None
            if ct.get("due_date"):
                try:
                    due_date = datetime.date.fromisoformat(ct["due_date"])
                except Exception:
                    due_date = target_end_date

            target_phase = first_phase
            if ct.get("phase_id"):
                found_phase = ProjectPhase.objects.filter(id=ct["phase_id"], project=project).first()
                if found_phase:
                    target_phase = found_phase

            ProjectTask.objects.create(
                project=project,
                phase=target_phase,
                title=ct.get("title", "Custom Milestone Task"),
                responsible_role=ct.get("responsible_role", "Custom Task"),
                assigned_to=assigned_user or created_by_admin,
                due_date=due_date or target_end_date,
                deliverables=ct.get("deliverables", []),
                status=ProjectTask.TaskStatus.TODO,
                priority=ct.get("priority", "Medium"),
                order=idx,
                is_custom=True,
            )

    return project
