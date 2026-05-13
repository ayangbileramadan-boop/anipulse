from django.db import models
from django.conf import settings
from apps.core.models import TimeStampedModel
from apps.anime.models import Anime


class WatchlistEntry(TimeStampedModel):
    class Status(models.TextChoices):
        WATCHING = 'WATCHING', 'Watching'
        COMPLETED = 'COMPLETED', 'Completed'
        PAUSED = 'PAUSED', 'Paused'
        DROPPED = 'DROPPED', 'Dropped'
        PLANNING = 'PLANNING', 'Planning to Watch'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='watchlist',
    )
    anime = models.ForeignKey(
        Anime,
        on_delete=models.CASCADE,
        related_name='watchlist_entries',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PLANNING,
        db_index=True,
    )
    episodes_watched = models.IntegerField(default=0)
    score = models.FloatField(null=True, blank=True)
    notes = models.TextField(blank=True)
    started_at = models.DateField(null=True, blank=True)
    completed_at = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'anime')
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', '-updated_at']),
        ]

    def __str__(self):
        return f"{self.user.username} — {self.anime} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if self.anime.episodes and self.episodes_watched >= self.anime.episodes:
            if self.status != self.Status.COMPLETED:
                self.status = self.Status.COMPLETED
        super().save(*args, **kwargs)


class CustomList(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='custom_lists',
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_public = models.BooleanField(default=True)
    anime = models.ManyToManyField(Anime, blank=True, related_name='custom_lists')

    class Meta:
        unique_together = ('user', 'name')
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.user.username} — {self.name}"


class Achievement(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='achievements',
    )
    key = models.CharField(max_length=50)
    title = models.CharField(max_length=100)
    description = models.TextField()
    icon = models.CharField(max_length=10, default='🏆')
    unlocked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'key')
        ordering = ['-unlocked_at']

    def __str__(self):
        return f"{self.user.username} — {self.title}"


ACHIEVEMENT_DEFS = {
    'first_anime': {'title': 'First Step', 'description': 'Added your first anime', 'icon': '🎬'},
    'watching_5': {'title': 'Getting Started', 'description': 'Watching 5 anime at once', 'icon': '📺'},
    'completed_10': {'title': 'Binge Watcher', 'description': 'Completed 10 anime', 'icon': '🍿'},
    'completed_50': {'title': 'Anime Veteran', 'description': 'Completed 50 anime', 'icon': '⭐'},
    'completed_100': {'title': 'Anime Master', 'description': 'Completed 100 anime', 'icon': '👑'},
    'watchlist_25': {'title': 'Collector', 'description': '25 anime on watchlist', 'icon': '📋'},
    'watchlist_100': {'title': 'Hoarder', 'description': '100 anime on watchlist', 'icon': '🗃️'},
    'review_first': {'title': 'Critic', 'description': 'Wrote your first review', 'icon': '✍️'},
    'review_10': {'title': 'Reviewer', 'description': 'Wrote 10 reviews', 'icon': '📝'},
    'list_creator': {'title': 'Curator', 'description': 'Created first custom list', 'icon': '📚'},
    'hours_100': {'title': 'Dedicated', 'description': '100+ hours watched', 'icon': '⏰'},
    'hours_500': {'title': 'Otaku', 'description': '500+ hours watched', 'icon': '🎌'},
    'quiz_first': {'title': 'Quizzer', 'description': 'Completed first quiz', 'icon': '🧠'},
    'quiz_perfect': {'title': 'Genius', 'description': 'Perfect quiz score', 'icon': '💎'},
}
