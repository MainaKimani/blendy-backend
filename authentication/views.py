from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.conf import settings
from django.contrib.auth import authenticate
from .models import UserSession
from .serializers import (
    UserSessionSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    PasswordChangeSerializer,
)
from users.models import CustomUser
from rest_framework_simplejwt.views import TokenObtainPairView
from datetime import datetime, timedelta
from django.utils import timezone
import hashlib
from rest_framework_simplejwt.tokens import RefreshToken


class LogoutView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        try:
            refresh_token = request.data["refresh_token"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={'detail': str(e)})


class UserSessionViewSet(viewsets.ModelViewSet):
    queryset = UserSession.objects.all()
    serializer_class = UserSessionSerializer


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            return Response(
                {"detail": "User with this email does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Generate token and UID
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        # In a real application, you would send an email with a link containing uid and token
        # For now, we'll just return them in the response for testing purposes
        print(f"Password reset link: /reset-password/{uid}/{token}/")
        return Response(
            {
                "detail": "Password reset link sent to your email (or printed to console for testing)."
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, uidb64, token, *args, **kwargs):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_password = serializer.validated_data["new_password"]

        try:
            uid = urlsafe_base64_decode(uidb64).decode()
            user = CustomUser.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
            user = None

        if user is not None and default_token_generator.check_token(user, token):
            user.set_password(new_password)
            user.save()
            return Response(
                {"detail": "Password has been reset successfully."},
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"detail": "The reset link is invalid or has expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        old_password = serializer.validated_data["old_password"]
        new_password = serializer.validated_data["new_password"]

        if not user.check_password(old_password):
            return Response(
                {"detail": "Current password is not correct."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(new_password)
        user.save()
        return Response(
            {"detail": "Password has been changed successfully."},
            status=status.HTTP_200_OK,
        )
