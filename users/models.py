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

    

    def get_permission_names(self):
        """Every permission granted to this user within their organization.

        Resolved in a single query. The previous implementation walked the role
        assignments in Python at three queries each, and returned early on a
        match — so its cost depended on role ordering, and the worst case was a
        permission the user did *not* hold, which is exactly the path a denied
        request takes.

        Deliberately not cached here: a permission set cached on the user object
        outlives the request whenever that object is reused, and would then hand
        back access that has since been revoked. HasUserPermission caches it on
        the request instead, where it cannot go stale.
        """
        if not self.organization_id:
            names = frozenset()
        else:
            names = frozenset(
                name
                for name in self.role_assignments.filter(
                    organization_role__organization_id=self.organization_id
                ).values_list(
                    'organization_role__role__permissions__name', flat=True
                )
                # A role with no permissions attached yields a null here.
                if name is not None
            )

        return names

    def has_perm(self, perm, obj=None):
        """Does the user have a specific permission?"""
        if self.is_superuser: # Django's built-in superuser has all permissions
            return True
        if self.is_superuser_admin: # Our custom super admin has all permissions
            return True

        return perm in self.get_permission_names()

    def has_module_perms(self, app_label):
        """Does the user have permissions to view the app `app_label`?"""
        if self.is_superuser or self.is_superuser_admin:
            return True
        # This is a simplified check; you might want to implement more granular module permissions
        return self.has_perm(f'view_{app_label}') # Example: check for a generic view permission

