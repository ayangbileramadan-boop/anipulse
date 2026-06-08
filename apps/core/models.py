from django.conf import settings
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='game_profile',
    )
    total_xp = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_user_profile'

    def __str__(self):
        return f"{self.user.username} (Lv.{self.level})"

    @property
    def level(self):
        from apps.core.services.gamification import level_for_xp
        return level_for_xp(self.total_xp)[0]

    @property
    def level_progress(self):
        from apps.core.services.gamification import level_for_xp, xp_for_level
        xp = self.total_xp or 0
        lvl, remainder = level_for_xp(xp)
        next_xp = xp_for_level(lvl + 1) - xp_for_level(lvl) if lvl < 50 else 1
        progress = min(remainder / max(next_xp, 1) * 100, 100) if next_xp > 0 else 100
        return {'level': lvl, 'xp': xp, 'progress_pct': round(progress, 1)}


class UserBadge(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='badges',
    )
    badge_id = models.CharField(max_length=50)
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'core_user_badge'
        unique_together = ('user', 'badge_id')

    def __str__(self):
        return f"{self.user.username}: {self.badge_id}"


class UserQuest(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='quests',
    )
    quest_id = models.CharField(max_length=50)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    progress = models.IntegerField(default=0)
    target = models.IntegerField(default=1)
    xp_reward = models.IntegerField(default=50)
    expires_at = models.DateTimeField()
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'core_user_quest'
        indexes = [
            models.Index(fields=['user', 'completed', 'expires_at']),
        ]

    def __str__(self):
        return f"{self.user.username}: {self.title} ({self.progress}/{self.target})"


class Streak(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='streak')
    current_streak = models.IntegerField(default=0)
    longest_streak = models.IntegerField(default=0)
    last_activity = models.DateField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'anime'

    def check_and_update(self):
        today = timezone.now().date()
        if self.last_activity:
            delta = (today - self.last_activity).days
            if delta == 1:
                self.current_streak += 1
            elif delta > 1:
                self.current_streak = 1
        else:
            self.current_streak = 1
        self.longest_streak = max(self.longest_streak, self.current_streak)
        self.last_activity = today
        self.save()

    def __str__(self):
        return f"{self.user.username}: {self.current_streak} day streak"


class UserFollow(models.Model):
    follower = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='following')
    following = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='followers')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'anime'
        unique_together = ('follower', 'following')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.follower} follows {self.following}"


class Notification(models.Model):
    class Type(models.TextChoices):
        FOLLOW = 'FOLLOW', 'Follow'
        LIKE = 'LIKE', 'Like'
        REVIEW = 'REVIEW', 'Review'
        COMMENT = 'COMMENT', 'Comment'
        TIER_LIST = 'TIER_LIST', 'Tier List'
        BATTLE_VOTE = 'BATTLE_VOTE', 'Battle Vote'
        LEVEL_UP = 'LEVEL_UP', 'Level Up'
        BADGE = 'BADGE', 'Badge'
        SYSTEM = 'SYSTEM', 'System'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=20, choices=Type.choices, default=Type.SYSTEM)
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    url = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'anime'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'is_read'])]

    def __str__(self):
        return f"{self.user.username}: {self.title}"


class CharacterFavorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='character_favorites')
    character_id = models.IntegerField()
    character_name = models.CharField(max_length=300)
    character_image = models.URLField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'anime'
        unique_together = ('user', 'character_id')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} fav {self.character_name}"


class StaffFavorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='staff_favorites')
    staff_id = models.IntegerField()
    staff_name = models.CharField(max_length=300)
    staff_image = models.URLField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'anime'
        unique_together = ('user', 'staff_id')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} fav {self.staff_name}"
