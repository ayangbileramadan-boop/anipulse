from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base model with created/updated timestamps."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserProfile(models.Model):
    """Gamification profile extension for User."""
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
    """A badge earned by a user."""
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
    """A daily or weekly quest for a user."""
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
