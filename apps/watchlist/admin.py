from django.contrib import admin
from .models import WatchlistEntry


@admin.register(WatchlistEntry)
class WatchlistEntryAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'anime', 'status', 'episodes_watched',
        'score', 'created_at', 'updated_at',
    ]
    list_filter = ['status', 'created_at']
    search_fields = ['user__username', 'anime__title_romaji', 'anime__title_english']
    raw_id_fields = ['user', 'anime']
    date_hierarchy = 'created_at'
