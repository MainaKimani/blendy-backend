from rest_framework import serializers
from django.db import transaction
from .models import Organization
from users.models import CustomUser
from users.serializers import CustomUserSerializer
from authorization.models import Role, OrganizationRole, UserRoleAssignment
from authorization.rbac import DEFAULT_ORGANIZATION_ROLES, ORG_ADMIN, ROLES
from pricing.services import create_default_pricelist

class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = '__all__'

class OnboardOrganizationSerializer(serializers.Serializer):
    """Serializer for onboarding a new organization and its admin user."""
    organization = OrganizationSerializer()
    user = CustomUserSerializer()

    def create(self, validated_data):
        org_data = validated_data.pop('organization')
        user_data = validated_data.pop('user')

        with transaction.atomic():
            # Create the organization
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