from rest_framework import serializers
from .models import Permission, Role, OrganizationRole, UserRoleAssignment
from users.serializers import CustomUserSerializer
from organization.serializers import OrganizationSerializer

class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = '__all__'

class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.PrimaryKeyRelatedField(many=True, queryset=Permission.objects.all())

    class Meta:
        model = Role
        fields = '__all__'

class OrganizationRoleSerializer(serializers.ModelSerializer):
    role = RoleSerializer(read_only=True)
    organization = OrganizationSerializer(read_only=True)
    # Both relations above are read-only so the response can nest them in full,
    # which left the serializer with nothing writable at all: a create wrote no
    # role and died on the not-null column. The organization is taken from the
    # tenant header, so the role is the one thing a caller has to supply.
    role_id = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.all(), source='role', write_only=True
    )

    class Meta:
        model = OrganizationRole
        fields = '__all__'

class UserRoleAssignmentSerializer(serializers.ModelSerializer):
    user = CustomUserSerializer(read_only=True)
    organization_role = OrganizationRoleSerializer(read_only=True)

    class Meta:
        model = UserRoleAssignment
        fields = '__all__'
