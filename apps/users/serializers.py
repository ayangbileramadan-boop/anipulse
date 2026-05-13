from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.authtoken.models import Token

User = get_user_model()


class UserPublicSerializer(serializers.ModelSerializer):
    """Safe read-only public profile."""
    watching_count = serializers.ReadOnlyField()
    completed_count = serializers.ReadOnlyField()
    planning_count = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'bio', 'avatar', 'cover_image',
            'date_joined', 'watching_count', 'completed_count', 'planning_count',
        ]
        read_only_fields = ['id', 'date_joined']


class UserPrivateSerializer(serializers.ModelSerializer):
    """Full profile for the authenticated user."""
    watching_count = serializers.ReadOnlyField()
    completed_count = serializers.ReadOnlyField()
    planning_count = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'bio', 'avatar', 'cover_image', 'timezone',
            'notify_new_episodes', 'notify_airing',
            'date_joined', 'watching_count', 'completed_count', 'planning_count',
        ]
        read_only_fields = ['id', 'date_joined']


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    token = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'password_confirm', 'token']

    def validate(self, attrs):
        if attrs['password'] != attrs.pop('password_confirm'):
            raise serializers.ValidationError({'password': 'Passwords do not match.'})
        return attrs

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user

    def get_token(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        return token.key


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({'new_password': 'Passwords do not match.'})
        return attrs

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Old password is incorrect.')
        return value
