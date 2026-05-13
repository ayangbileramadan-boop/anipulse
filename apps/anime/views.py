import time
import logging

from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

from apps.core.utils import get_current_season
from .models import Anime, Episode
from .serializers import (
    AnimeListSerializer, AnimeDetailSerializer,
    EpisodeSerializer,
)
from .filters import AnimeFilter
from .services.anilist import anilist_client, AniListError

logger = logging.getLogger(__name__)


class AnimeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Main anime endpoint. Reads from local DB (fast).
    Live AniList data available via dedicated actions.
    """
    queryset = (
        Anime.objects
        .filter(is_adult=False)
        .prefetch_related('genres', 'studios', 'external_links')
    )
    filterset_class = AnimeFilter
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title_romaji', 'title_english', 'title_native']
    ordering_fields = ['trending', 'popularity', 'average_score', 'season_year', 'created_at']
    ordering = ['-trending']
    lookup_field = 'slug'

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return AnimeDetailSerializer
        return AnimeListSerializer

    # ─── Live AniList Actions ─────────────────────────────────────

    @action(detail=False, methods=['get'], url_path='trending')
    def trending(self, request):
        """Top trending from AniList (cached 1h)."""
        try:
            page = max(1, int(request.query_params.get('page', 1)))
            per_page = min(50, int(request.query_params.get('per_page', 20)))
            data = anilist_client.get_trending(page=page, per_page=per_page)
            return Response(data['Page'])
        except AniListError as e:
            return Response({'error': 'AniList API error'}, status=status.HTTP_502_BAD_GATEWAY)

    @action(detail=False, methods=['get'], url_path='popular-this-season')
    def popular_this_season(self, request):
        """Popular anime for the current season."""
        season, year = get_current_season()
        try:
            data = anilist_client.get_popular_this_season(
                season=request.query_params.get('season', season),
                year=int(request.query_params.get('year', year)),
                page=int(request.query_params.get('page', 1)),
            )
            return Response(data['Page'])
        except AniListError:
            return Response({'error': 'AniList API error'}, status=status.HTTP_502_BAD_GATEWAY)

    @action(detail=False, methods=['get'], url_path='airing-today')
    def airing_today(self, request):
        """Anime airing in the next 24 hours."""
        now = int(time.time())
        end = now + (24 * 60 * 60)
        try:
            data = anilist_client.get_airing_schedule(week_start=now, week_end=end)
            # Filter out adult content
            schedules = [
                s for s in data['Page']['airingSchedules']
                if not s['media'].get('isAdult', False)
            ]
            return Response({'airingSchedules': schedules, 'pageInfo': data['Page']['pageInfo']})
        except AniListError:
            return Response({'error': 'AniList API error'}, status=status.HTTP_502_BAD_GATEWAY)

    @action(detail=False, methods=['get'], url_path='calendar')
    def calendar(self, request):
        """Full 7-day airing schedule."""
        now = int(time.time())
        week_end = now + (7 * 24 * 60 * 60)
        try:
            data = anilist_client.get_airing_schedule(week_start=now, week_end=week_end)
            schedules = [
                s for s in data['Page']['airingSchedules']
                if not s['media'].get('isAdult', False)
            ]
            return Response({'airingSchedules': schedules})
        except AniListError:
            return Response({'error': 'AniList API error'}, status=status.HTTP_502_BAD_GATEWAY)

    @action(detail=False, methods=['get'], url_path='search')
    def search_anime(self, request):
        """Live search through AniList."""
        q = request.query_params.get('q')
        try:
            data = anilist_client.search(
                search=q if q else None,
                genres=request.query_params.getlist('genres') or None,
                format=request.query_params.get('format') or None,
                status=request.query_params.get('status') or None,
                season=request.query_params.get('season') or None,
                year=int(request.query_params['year']) if request.query_params.get('year') else None,
                sort=request.query_params.getlist('sort') or ['TRENDING_DESC'],
                page=int(request.query_params.get('page', 1)),
                per_page=int(request.query_params.get('per_page', 20)),
            )
            return Response(data['Page'])
        except AniListError:
            return Response({'error': 'AniList API error'}, status=status.HTTP_502_BAD_GATEWAY)

    @action(detail=True, methods=['get'], url_path='live')
    def live_detail(self, request, slug=None):
        """Fetch full detail directly from AniList by AniList ID."""
        anime = self.get_object()
        try:
            data = anilist_client.get_anime_detail(anime.anilist_id)
            return Response(data['Media'])
        except AniListError:
            return Response({'error': 'AniList API error'}, status=status.HTTP_502_BAD_GATEWAY)

    @action(detail=True, methods=['get'], url_path='episodes')
    def episodes(self, request, slug=None):
        """Local episode list for an anime."""
        anime = self.get_object()
        episodes = Episode.objects.filter(anime=anime)
        serializer = EpisodeSerializer(episodes, many=True)
        return Response(serializer.data)


class AnimeDetailAPIView(viewsets.ViewSet):
    """Fetch anime detail directly from AniList by ID."""
    permission_classes = []

    def retrieve(self, request, pk=None):
        try:
            data = anilist_client.get_anime_detail(int(pk))
            return Response(data['Media'])
        except AniListError:
            return Response({'error': 'AniList API error'}, status=status.HTTP_502_BAD_GATEWAY)
        except ValueError:
            return Response({'error': 'Invalid anime ID'}, status=status.HTTP_400_BAD_REQUEST)
