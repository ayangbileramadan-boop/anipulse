from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    UserPublicSerializer, UserPrivateSerializer,
    RegisterSerializer, ChangePasswordSerializer,
)

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    """POST /api/v1/users/register/ — create account & return token."""
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class LoginView(ObtainAuthToken):
    """POST /api/v1/users/login/ — returns auth token."""
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        token = Token.objects.get(key=response.data['token'])
        serializer = UserPrivateSerializer(token.user)
        return Response({
            'token': token.key,
            'user': serializer.data,
        })


class LogoutView(APIView):
    """DELETE /api/v1/users/logout/ — revoke token."""
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request):
        request.user.auth_token.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/users/me/ — own profile."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserPrivateSerializer

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    """POST /api/v1/users/me/change-password/"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save()
        # Rotate token
        request.user.auth_token.delete()
        token = Token.objects.create(user=request.user)
        return Response({'token': token.key})


class UserProfileView(generics.RetrieveAPIView):
    """GET /api/v1/users/<username>/ — public profile."""
    serializer_class = UserPublicSerializer
    lookup_field = 'username'
    queryset = User.objects.all()
    permission_classes = [permissions.AllowAny]
