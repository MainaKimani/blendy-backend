from rest_framework import serializers
from django.db import transaction
from .models import Organization
from users.models import CustomUser
from users.serializers import CustomUserSerializer
from authorization.models import Role, OrganizationRole, UserRoleAssignment

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

            # Create the user and assign them to the organization
            user_data['organization'] = organization
            user = CustomUser.objects.create_user(**user_data)

            # Assign the ORG_ADMIN role to the newly created user
            # Ensure a global 'ORG_ADMIN' role exists
            org_admin_role, created = Role.objects.get_or_create(name='ORG_ADMIN', defaults={'description': 'Organization Administrator'})
            
            # Link the global ORG_ADMIN role to the new organization
            organization_admin_role, created = OrganizationRole.objects.get_or_create(
                organization=organization,
                role=org_admin_role
            )
            
            # Assign the user to this organization-specific admin role
            UserRoleAssignment.objects.create(user=user, organization_role=organization_admin_role)

            # Set is_organization_admin flag on the user for convenience/legacy checks
            user.is_organization_admin = True
            user.save()
        
        return {'organization': organization, 'user': user}