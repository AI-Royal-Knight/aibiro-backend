from django.core.management.base import BaseCommand
from app.accounts.models import UserAccount
from app.projects.models import (
    ServiceWorkflowTemplate,
    ServicePhaseTemplate,
    ServiceTaskTemplate,
)
from app.projects.services_data import SERVICES_LIBRARY


class Command(BaseCommand):
    help = "Seeds predefined service workflow templates, phases, tasks, and sets demo staff functional roles"

    def handle(self, *args, **options):
        # 1. Update demo users with realistic functional roles for auto-assignment
        role_assignments = {
            "staff@gmail.com": [
                "Compliance Architect",
                "Policy Specialist",
                "Policy & Documentation Specialist",
                "HR Policy Specialist",
                "Compliance Analyst",
                "Documentation Specialist",
            ],
            "admin@gmail.com": [
                "Engagement Lead",
                "Project Manager",
                "Operations Consultant",
                "Operations Architect",
                "Healthcare Operations Architect",
                "Implementation Manager",
            ],
            "qareviewer@gmail.com": [
                "Quality Specialist",
                "Quality & Performance Improvement Specialist",
                "Clinical Operations Consultant",
                "Clinical Consultant",
                "Clinical Specialist",
                "Utilization Review Specialist",
                "UR Specialist",
            ],
            "superadmin@gmail.com": [
                "Engagement Lead",
                "Compliance Architect",
                "Regulatory Compliance Architect",
                "Risk Specialist",
                "Risk Management Specialist",
                "Data Analyst",
                "Data Specialist",
                "Licensing Specialist",
                "Revenue Specialist",
            ],
        }

        for email, roles in role_assignments.items():
            user = UserAccount.objects.filter(email=email).first()
            if user:
                user.functional_roles = roles
                user.save(update_fields=["functional_roles"])
                self.stdout.write(self.style.SUCCESS(f"Updated {email} functional roles: {roles}"))

        # 2. Seed service workflow templates
        created_count = 0
        for s_data in SERVICES_LIBRARY:
            template, created = ServiceWorkflowTemplate.objects.update_or_create(
                slug=s_data["slug"],
                defaults={
                    "name": s_data["name"],
                    "category": s_data.get("category", ""),
                    "category_label": s_data.get("category_label", ""),
                    "tagline": s_data.get("tagline", ""),
                    "description": s_data.get("description", ""),
                    "duration_weeks": s_data.get("duration_weeks", 12),
                    "programs": s_data.get("programs", []),
                    "standards_alignment": s_data.get("standards_alignment", []),
                    "team_roles": s_data.get("team_roles", []),
                    "quote_range": s_data.get("quote_range", ""),
                    "is_active": True,
                },
            )

            # Recreate phases and tasks to ensure 100% exact alignment with PDF
            ServiceTaskTemplate.objects.filter(phase_template__service_template=template).delete()
            ServicePhaseTemplate.objects.filter(service_template=template).delete()

            for p_data in s_data.get("phases", []):
                phase_tpl = ServicePhaseTemplate.objects.create(
                    service_template=template,
                    phase_number=p_data["phase_number"],
                    name=p_data["name"],
                    objective=p_data.get("objective", ""),
                    responsible_role=p_data.get("responsible_role", "Engagement Lead"),
                    week_start=p_data.get("week_start", 1),
                    week_end=p_data.get("week_end", 2),
                )

                for idx, t_data in enumerate(p_data.get("tasks", []), start=1):
                    ServiceTaskTemplate.objects.create(
                        phase_template=phase_tpl,
                        title=t_data["title"],
                        responsible_role=t_data.get("responsible_role", "Compliance Architect"),
                        deliverables=t_data.get("deliverables", []),
                        relative_due_week=t_data.get("relative_due_week", 1),
                        order=idx,
                    )

            created_count += 1
            self.stdout.write(self.style.SUCCESS(f"Loaded service template: {template.name}"))

        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {created_count} service templates!"))
