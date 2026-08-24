from rest_framework import serializers
from django.db import transaction
from .models import Organization, PlatformAccessLog
from users.models import CustomUser
from users.serializers import CustomUserSerializer
from authorization.models import Role, OrganizationRole, UserRoleAssignment
from authorization.rbac import DEFAULT_ORGANIZATION_ROLES, ORG_ADMIN, ROLES
from pricing.services import create_default_pricelist

class OrganizationSerializer(serializers.ModelSerializer):
    # Declared explicitly rather than left to read_only_fields: the partial
    # unique constraint on this column makes DRF generate a UniqueValidator for
    # it, which then rejects any payload that mentions the field at all. An
    # explicitly read-only field gets no validator, and a client's opinion on
    # whether an organization is Blendy's own HQ is not wanted either way.
    is_platform = serializers.BooleanField(read_only=True)

    class Meta:
        model = Organization
        fields = '__all__'

class PlatformAccessLogSerializer(serializers.ModelSerializer):
    """Read-only throughout: an audit record nobody may edit is the point."""

    class Meta:
        model = PlatformAccessLog
        fields = (
            "id",
            "actor",
            "actor_email",
            "organization",
            "organization_slug",
            "method",
            "path",
            "status_code",
            "granted",
            "created_at",
        )
        read_only_fields = fields


class TenantAccessLogSerializer(serializers.ModelSerializer):
    """The same records, shown to the organization they are about.

    Differs from PlatformAccessLogSerializer in one respect, and it is the whole
    point of having a second serializer: `actor` is named only when they were
    Blendy staff.

    Naming a Blendy employee is the honest answer to "who looked at my data?"
    and is what makes the support relationship legible. Naming a *different
    customer* whose access was refused would hand one shop the email address of
    another shop's staff — leaking across exactly the boundary this log exists
    to watch. Those rows still appear, because a refused attempt is worth
    knowing about; they simply do not identify the person.
    """

    actor = serializers.SerializerMethodField()

    class Meta:
        model = PlatformAccessLog
        fields = (
            "id",
            "actor",
            "actor_is_platform",
            "method",
            "path",
            "status_code",
            "granted",
            "created_at",
        )
        read_only_fields = fields

    def get_actor(self, obj):
        if obj.actor_is_platform:
            return obj.actor_email
        return "an account outside this organization"


class OnboardOrganizationSerializer(serializers.Serializer):
    """Serializer for onboarding a new organization and its admin user."""
    organization = OrganizationSerializer()
    user = CustomUserSerializer()

    def create(self, validated_data):
        org_data = validated_data.pop('organization')
        user_data = validated_data.pop('user')

        with transaction.atomic():
            # Create the organization. Onboarding produces customers only —
            # HQ is created by migration and `manage.py bootstrap_hq`, and gets
            # neither a pricelist nor shop roles because it never sells.
            org_data.pop("is_platform", None)
            organization = Organization.objects.create(**org_data)

            # Sales are priced from the default pricelist, so an organization
            # without one cannot trade at all. Create it up front.
            create_default_pricelist(organization)

            # Create the user and assign them to the organization
            user_data['organization'] = organization
            user = CustomUser.objects.create_user(**user_data)

            # Enable the built-in roles for this shop. ORG_ADMIN is what the
            # owner gets; CASHIER is enabled alongside it so the owner can hire
            # staff straight away rather than having to enable the role first.
            # The roles and their permissions are seeded by authorization.rbac.
            organization_roles = {}
            for role_name in DEFAULT_ORGANIZATION_ROLES:
                role, _ = Role.objects.get_or_create(
                    name=role_name,
                    defaults={'description': ROLES[role_name]['description']},
                )
                organization_roles[role_name], _ = OrganizationRole.objects.get_or_create(
                    organization=organization, role=role
                )

            organization_admin_role = organization_roles[ORG_ADMIN]
            
            # Assign the user to this organization-specific admin role
            UserRoleAssignment.objects.create(user=user, organization_role=organization_admin_role)

            # Set is_organization_admin flag on the user for convenience/legacy checks
            user.is_organization_admin = True
            user.save()
        
        return {'organization': organization, 'user': user}