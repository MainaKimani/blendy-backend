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

    class Meta:
        model = OrganizationRole
        fields = '__all__'

class UserRoleAssignmentSerializer(serializers.ModelSerializer):
    user = CustomUserSerializer(read_only=True)
    organization_role = OrganizationRoleSerializer(read_only=True)

    class Meta:
        model = UserRoleAssignment
        fields = '__all__'
