from django.core.management.base import BaseCommand
from app.accounts.models import UserAccount

class Command(BaseCommand):
    help = "Creates demo users for each role (e.g. superadmin@gmail.com, admin@gmail.com, etc.)"

    def handle(self, *args, **options):
        password = "1fjw0676"
        roles = UserAccount.Role.choices
        
        for role_value, role_label in roles:
            # Remove underscores for the email prefix, e.g. super_admin -> superadmin
            prefix = role_value.replace("_", "")
            email = f"{prefix}@gmail.com"
            
            user, created = UserAccount.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": "Demo",
                    "last_name": str(role_label),
                    "role": role_value,
                    "is_verified": True,
                    "is_active": True,
                }
            )
            
            if not created:
                user.role = role_value
                user.is_verified = True
                user.is_active = True
                
            user.set_password(password)
            
            # Ensure super admin has Django admin access
            if role_value == UserAccount.Role.SUPER_ADMIN:
                user.is_superuser = True
                user.is_staff = True
            
            # Grant staff access for roles that are staff members
            if user.is_staff_member:
                user.is_staff = True
                
            user.save()
            
            action = "Created" if created else "Updated"
            self.stdout.write(
                self.style.SUCCESS(f"{action} demo user: {email} | Role: {role_value}")
            )
            
        self.stdout.write(self.style.SUCCESS("All demo users are ready to use!"))
