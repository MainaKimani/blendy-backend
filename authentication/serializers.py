from rest_framework import serializers
from .models import UserSession
from users.models import CustomUser
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class UserSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSession
        fields = '__all__'

class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, write_only=True)

class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True)

class CustomLoginSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Add custom claims
        token['email'] = user.email
        token['user_id'] = str(user.id)
        if user.organization:
            token['organization_id'] = str(user.organization.id)

        return token

    def validate(self, attrs):
        data = super().validate(attrs)

        # Add custom data to the response
        data['user_id'] = str(self.user.id)
        data['email'] = self.user.email
        data["name"] = self.user.first_name + ' ' + self.user.last_name
        if self.user.organization:
            data['organization'] = str(self.user.organization.id)

        return data
