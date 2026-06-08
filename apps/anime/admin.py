from django.contrib import admin
from .models import Anime, Episode, Genre, Studio, ExternalLink, Tag, AnimeTag, Review, DiscussionThread, DiscussionComment, FavoriteAnime


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']


@admin.register(Studio)
class StudioAdmin(admin.ModelAdmin):
    list_display = ['name', 'anilist_id']
    search_fields = ['name']


class ExternalLinkInline(admin.TabularInline):
    model = ExternalLink
    extra = 0
    fields = ['site', 'url', 'color']


class EpisodeInline(admin.TabularInline):
    model = Episode
    extra = 0
    fields = ['number', 'title', 'air_date']


@admin.register(Anime)
class AnimeAdmin(admin.ModelAdmin):
    list_display = [
        'display_title', 'anilist_id', 'format', 'status',
        'season', 'season_year', 'average_score', 'trending', 'popularity',
        'last_synced_at',
    ]
    list_filter = ['status', 'format', 'season', 'season_year', 'is_adult']
    search_fields = ['title_romaji', 'title_english', 'anilist_id']
    readonly_fields = ['created_at', 'updated_at', 'last_synced_at', 'slug']
    filter_horizontal = ['genres', 'studios']
    inlines = [ExternalLinkInline, EpisodeInline]

    fieldsets = (
        ('Identity', {
            'fields': ('anilist_id', 'slug', 'title_romaji', 'title_english', 'title_native')
        }),
        ('Media Info', {
            'fields': ('format', 'status', 'description', 'episodes', 'duration',
                       'season', 'season_year', 'start_date', 'end_date', 'is_adult')
        }),
        ('Scores', {
            'fields': ('average_score', 'mean_score', 'popularity', 'trending', 'favourites')
        }),
        ('Images', {
            'fields': ('cover_image_large', 'cover_image_medium', 'cover_image_color', 'banner_image')
        }),
        ('Airing', {
            'fields': ('next_airing_episode', 'next_airing_at')
        }),
        ('Relations', {
            'fields': ('genres', 'studios')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'last_synced_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['user', 'anime', 'rating', 'is_spoiler', 'likes', 'created_at']
    list_filter = ['rating', 'is_spoiler']
    search_fields = ['user__username', 'anime__title_romaji', 'anime__title_english']
    readonly_fields = ['created_at', 'updated_at']


class CommentInline(admin.TabularInline):
    model = DiscussionComment
    extra = 0
    fields = ['user', 'body', 'is_spoiler', 'created_at']
    readonly_fields = ['created_at']


@admin.register(DiscussionThread)
class DiscussionThreadAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'anime', 'episode_number', 'is_spoiler', 'is_pinned', 'views', 'created_at']
    list_filter = ['is_spoiler', 'is_pinned']
    search_fields = ['title', 'user__username', 'anime__title_romaji']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [CommentInline]


@admin.register(DiscussionComment)
class DiscussionCommentAdmin(admin.ModelAdmin):
    list_display = ['user', 'thread', 'is_spoiler', 'created_at']
    list_filter = ['is_spoiler']
    search_fields = ['user__username', 'thread__title', 'body']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(FavoriteAnime)
class FavoriteAnimeAdmin(admin.ModelAdmin):
    list_display = ['user', 'anime', 'created_at']
    search_fields = ['user__username', 'anime__title']
    autocomplete_fields = ['user', 'anime']
