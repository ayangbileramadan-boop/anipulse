from django.contrib import admin

from apps.core.models import UserProfile, UserBadge, UserQuest


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'total_xp', 'level_display', 'created_at']
    search_fields = ['user__username']
    list_select_related = ['user']

    def level_display(self, obj):
        return f"Lv.{obj.level}"
    level_display.short_description = 'Level'


@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display = ['user', 'badge_id', 'earned_at']
    list_filter = ['badge_id', 'earned_at']
    search_fields = ['user__username', 'badge_id']
    date_hierarchy = 'earned_at'


@admin.register(UserQuest)
class UserQuestAdmin(admin.ModelAdmin):
    list_display = ['user', 'title', 'progress', 'target', 'completed', 'expires_at']
    list_filter = ['completed', 'expires_at']
    search_fields = ['user__username', 'title']
