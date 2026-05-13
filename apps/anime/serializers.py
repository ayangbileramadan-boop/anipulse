from rest_framework import serializers
from .models import Anime, Episode, Genre, Studio, ExternalLink, Tag


class GenreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Genre
        fields = ['id', 'name']


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name', 'is_general_spoiler']


class StudioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Studio
        fields = ['id', 'name', 'anilist_id', 'site_url']


class ExternalLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExternalLink
        fields = ['id', 'site', 'url', 'icon', 'color', 'language']


class AnimeListSerializer(serializers.ModelSerializer):
    """Lightweight — for cards and list views."""
    display_title = serializers.ReadOnlyField()
    genres = GenreSerializer(many=True, read_only=True)

    class Meta:
        model = Anime
        fields = [
            'id', 'anilist_id', 'slug', 'display_title',
            'title_romaji', 'title_english',
            'cover_image_large', 'cover_image_medium', 'cover_image_color',
            'banner_image', 'format', 'status', 'episodes', 'duration',
            'average_score', 'season', 'season_year', 'trending', 'popularity',
            'next_airing_episode', 'next_airing_at', 'genres',
        ]


class AnimeDetailSerializer(serializers.ModelSerializer):
    """Full serializer for the detail page."""
    display_title = serializers.ReadOnlyField()
    trailer_url = serializers.ReadOnlyField()
    genres = GenreSerializer(many=True, read_only=True)
    studios = StudioSerializer(many=True, read_only=True)
    external_links = ExternalLinkSerializer(many=True, read_only=True)

    class Meta:
        model = Anime
        fields = [
            'id', 'anilist_id', 'slug', 'display_title',
            'title_romaji', 'title_english', 'title_native',
            'description', 'cover_image_large', 'cover_image_medium',
            'cover_image_color', 'banner_image',
            'format', 'status', 'episodes', 'duration',
            'average_score', 'mean_score', 'popularity', 'trending', 'favourites',
            'season', 'season_year', 'start_date', 'end_date',
            'next_airing_episode', 'next_airing_at',
            'site_url', 'trailer_url',
            'genres', 'studios', 'external_links',
            'created_at', 'updated_at', 'last_synced_at',
        ]


class EpisodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Episode
        fields = ['id', 'number', 'title', 'thumbnail', 'air_date', 'duration']


class AnimeSearchResultSerializer(serializers.Serializer):
    """Passthrough serializer for raw AniList search results."""
    id = serializers.IntegerField()
    title = serializers.DictField()
    coverImage = serializers.DictField()
    averageScore = serializers.IntegerField(allow_null=True)
    format = serializers.CharField(allow_null=True)
    status = serializers.CharField(allow_null=True)
    episodes = serializers.IntegerField(allow_null=True)
    season = serializers.CharField(allow_null=True)
    seasonYear = serializers.IntegerField(allow_null=True)
    genres = serializers.ListField(child=serializers.CharField())
