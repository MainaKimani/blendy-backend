from rest_framework import serializers
from .models import CustomUser, SalesAgentProfile
from authorization.models import OrganizationRole, UserRoleAssignment


class CustomUserSerializer(serializers.ModelSerializer):
    organization_role_ids = serializers.ListField(
        child=serializers.UUIDField(), write_only=True, required=False
    )
    assigned_roles = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = (
            "id",
            "username",
            "email",
            "password",
            "first_name",
            "last_name",
            "phone_number",
            "organization",
            "organization_role_ids",
            "assigned_roles",
        )
        extra_kwargs = {"password": {"write_only": True}}

    def get_assigned_roles(self, obj):
        # This method will return the names of the roles assigned to the user
        return [
            assignment.organization_role.role.name
            for assignment in obj.role_assignments.all()
        ]

    def create(self, validated_data):
        organization_role_ids = validated_data.pop("organization_role_ids", [])
        user = CustomUser.objects.create_user(**validated_data)

        # Assign roles
        self._assign_roles(user, organization_role_ids)
        return user

    def update(self, instance, validated_data):
        organization_role_ids = validated_data.pop("organization_role_ids", None)

        # Update user fields
        for attr, value in validated_data.items():
            if attr == "password":
                instance.set_password(value)
            else:
                setattr(instance, attr, value)
        instance.save()

        # Update roles if provided
        if organization_role_ids is not None:
            self._assign_roles(instance, organization_role_ids)

        return instance

    def _assign_roles(self, user, organization_role_ids):
        # Clear existing assignments for the user within their organization
        UserRoleAssignment.objects.filter(
            user=user, organization_role__organization=user.organization
        ).delete()

        # Assign new roles
        for org_role_id in organization_role_ids:
            try:
                org_role = OrganizationRole.objects.get(
                    id=org_role_id, organization=user.organization
                )
                UserRoleAssignment.objects.create(user=user, organization_role=org_role)
            except OrganizationRole.DoesNotExist:
                # Handle case where provided org_role_id does not exist or is not for this organization
                raise serializers.ValidationError(
                    f"Organization role with ID {org_role_id} not found or not valid for this organization."
                )


class SalesAgentProfileSerializer(serializers.ModelSerializer):
    user = CustomUserSerializer(read_only=True)

    class Meta:
        model = SalesAgentProfile
        fields = "__all__"
