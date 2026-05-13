from rest_framework import serializers
from apps.anime.serializers import AnimeListSerializer
from .models import WatchlistEntry


class WatchlistEntrySerializer(serializers.ModelSerializer):
    anime = AnimeListSerializer(read_only=True)
    anime_id = serializers.PrimaryKeyRelatedField(
        queryset=__import__('apps.anime.models', fromlist=['Anime']).Anime.objects.all(),
        source='anime',
        write_only=True,
    )

    class Meta:
        model = WatchlistEntry
        fields = [
            'id', 'anime', 'anime_id', 'status', 'episodes_watched',
            'score', 'notes', 'started_at', 'completed_at',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_episodes_watched(self, value):
        if value < 0:
            raise serializers.ValidationError('Episodes watched cannot be negative.')
        return value

    def validate_score(self, value):
        if value is not None and not (0 <= value <= 10):
            raise serializers.ValidationError('Score must be between 0 and 10.')
        return value


class WatchlistEntryCreateSerializer(serializers.ModelSerializer):
    """Simplified create-only serializer."""
    anime_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = WatchlistEntry
        fields = ['anime_id', 'status', 'episodes_watched', 'score']

    def create(self, validated_data):
        from apps.anime.models import Anime
        anime_id = validated_data.pop('anime_id')
        anime = Anime.objects.get(id=anime_id)
        validated_data['anime'] = anime
        return super().create(validated_data)
