from rest_framework import serializers
from apps.anime.models import Anime, Genre, Tag, Studio, Review, DiscussionThread, DiscussionComment
from apps.watchlist.models import WatchlistEntry, CustomList


class GenreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Genre
        fields = ['id', 'name']


class AnimeListSerializer(serializers.ModelSerializer):
    genres = GenreSerializer(many=True, read_only=True)

    class Meta:
        model = Anime
        fields = [
            'id', 'anilist_id', 'title_romaji', 'title_english', 'title_native',
            'slug', 'format', 'status', 'episodes', 'duration',
            'average_score', 'popularity', 'trending',
            'cover_image_large', 'cover_image_medium', 'genres',
        ]


class AnimeDetailSerializer(serializers.ModelSerializer):
    genres = GenreSerializer(many=True, read_only=True)

    class Meta:
        model = Anime
        fields = [
            'id', 'anilist_id', 'title_romaji', 'title_english', 'title_native',
            'slug', 'format', 'status', 'description', 'episodes', 'duration',
            'season', 'season_year', 'start_date', 'end_date',
            'average_score', 'mean_score', 'popularity', 'trending', 'favourites',
            'cover_image_large', 'cover_image_medium', 'banner_image',
            'genres', 'is_adult', 'site_url',
        ]


class WatchlistEntrySerializer(serializers.ModelSerializer):
    anime = AnimeListSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = WatchlistEntry
        fields = [
            'id', 'anime', 'status', 'status_display',
            'episodes_watched', 'score', 'started_at', 'completed_at',
            'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['user', 'created_at', 'updated_at']


class WatchlistEntryWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = WatchlistEntry
        fields = [
            'status', 'episodes_watched', 'score', 'notes',
            'started_at', 'completed_at',
        ]


class ReviewSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    anime_title = serializers.CharField(source='anime.display_title', read_only=True)

    class Meta:
        model = Review
        fields = [
            'id', 'anime', 'anime_title', 'username', 'rating',
            'title', 'body', 'is_spoiler', 'likes', 'created_at',
        ]
        read_only_fields = ['user', 'likes', 'created_at', 'updated_at']


class DiscussionThreadSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    comment_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = DiscussionThread
        fields = [
            'id', 'anime', 'username', 'title', 'body',
            'episode_number', 'is_spoiler', 'is_pinned',
            'likes', 'views', 'comment_count', 'created_at',
        ]
        read_only_fields = ['user', 'likes', 'views', 'created_at', 'updated_at']


class DiscussionCommentSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = DiscussionComment
        fields = [
            'id', 'thread', 'username', 'body',
            'is_spoiler', 'parent', 'likes', 'created_at',
        ]
        read_only_fields = ['user', 'likes', 'created_at', 'updated_at']


class CustomListSerializer(serializers.ModelSerializer):
    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = CustomList
        fields = ['id', 'name', 'description', 'is_public', 'item_count', 'created_at']
        read_only_fields = ['user', 'created_at', 'updated_at']
