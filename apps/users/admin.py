from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'date_joined', 'is_active', 'is_staff']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('AniPulse', {
            'fields': ('bio', 'avatar', 'cover_image', 'timezone',
                       'notify_new_episodes', 'notify_airing')
        }),
    )
