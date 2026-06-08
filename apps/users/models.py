from django.contrib.auth.models import AbstractUser
from django.db import models
from apps.core.models import TimeStampedModel


class User(AbstractUser):
    bio = models.TextField(blank=True)
    avatar = models.URLField(max_length=500, blank=True)
    cover_image = models.URLField(max_length=500, blank=True)
    timezone = models.CharField(max_length=50, default='UTC')
    is_watchlist_public = models.BooleanField(default=True)

    # Notification prefs
    notify_new_episodes = models.BooleanField(default=True)
    notify_airing = models.BooleanField(default=True)

    class Meta:
        db_table = 'users_user'

    def __str__(self):
        return self.username

    @property
    def watching_count(self):
        return self.watchlist.filter(status='WATCHING').count()

    @property
    def completed_count(self):
        return self.watchlist.filter(status='COMPLETED').count()

    @property
    def planning_count(self):
        return self.watchlist.filter(status='PLANNING').count()
