from datetime import datetime, timedelta
import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
import jwt
from django.conf import settings
from organization.models import Organization

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_superuser_admin', True) # New field for super admin

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)

class CustomUser(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='users', null=True, blank=True)
    username = models.CharField(max_length=255, unique=True)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=255, blank=True)
    last_name = models.CharField(max_length=255, blank=True)
    phone_number = models.CharField(max_length=255, blank=True)
    # Removed 'role' field
    region = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_organization_admin = models.BooleanField(default=False)
    is_superuser_admin = models.BooleanField(default=False) # New field for super admin
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login = models.DateTimeField(blank=True, null=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.email

    

    def has_perm(self, perm, obj=None):
        """Does the user have a specific permission?"""
        if self.is_superuser: # Django's built-in superuser has all permissions
            return True
        if self.is_superuser_admin: # Our custom super admin has all permissions
            return True

        # Check permissions through assigned roles
        if self.organization and hasattr(self, 'role_assignments'):
            for assignment in self.role_assignments.filter(organization_role__organization=self.organization):
                for permission in assignment.organization_role.role.permissions.all():
                    if permission.name == perm:
                        return True
        return False

    def has_module_perms(self, app_label):
        """Does the user have permissions to view the app `app_label`?"""
        if self.is_superuser or self.is_superuser_admin:
            return True
        # This is a simplified check; you might want to implement more granular module permissions
        return self.has_perm(f'view_{app_label}') # Example: check for a generic view permission

class SalesAgentProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, primary_key=True, related_name='sales_profile')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    employee_id = models.CharField(max_length=100, unique=True)
    sales_target = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    region_assigned = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"Profile: {self.user.username}"
