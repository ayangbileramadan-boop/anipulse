from django.contrib import admin

from apps.core.models import UserProfile, UserBadge, UserQuest, Streak, UserFollow, Notification, CharacterFavorite, StaffFavorite


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


@admin.register(Streak)
class StreakAdmin(admin.ModelAdmin):
    list_display = ['user', 'current_streak', 'longest_streak', 'last_activity']
    search_fields = ['user__username']


@admin.register(UserFollow)
class UserFollowAdmin(admin.ModelAdmin):
    list_display = ['follower', 'following', 'created_at']
    search_fields = ['follower__username', 'following__username']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'title', 'is_read', 'created_at']
    list_filter = ['is_read', 'created_at']
    search_fields = ['user__username', 'title']
    date_hierarchy = 'created_at'


@admin.register(CharacterFavorite)
class CharacterFavoriteAdmin(admin.ModelAdmin):
    list_display = ['user', 'character_name', 'created_at']
    search_fields = ['user__username', 'character_name']


@admin.register(StaffFavorite)
class StaffFavoriteAdmin(admin.ModelAdmin):
    list_display = ['user', 'staff_name', 'created_at']
    search_fields = ['user__username', 'staff_name']
