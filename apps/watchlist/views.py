from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import WatchlistEntry
from .serializers import WatchlistEntrySerializer, WatchlistEntryCreateSerializer
from apps.anime.services.anilist import anilist_client, AniListError
from apps.anime.services.sync import sync_anime_from_anilist


class WatchlistViewSet(viewsets.ModelViewSet):
    """
    User's personal watchlist. All entries are scoped to the authenticated user.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = WatchlistEntrySerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status']
    ordering_fields = ['updated_at', 'created_at', 'score']
    ordering = ['-updated_at']

    def get_queryset(self):
        return (
            WatchlistEntry.objects
            .filter(user=self.request.user)
            .select_related('anime')
            .prefetch_related('anime__genres')
        )

    def get_serializer_class(self):
        if self.action == 'create':
            return WatchlistEntryCreateSerializer
        return WatchlistEntrySerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['post'])
    def add_anilist(self, request):
        """POST /watchlist/add_anilist/ — sync from AniList then add to watchlist."""
        anilist_id = request.data.get('anilist_id')
        watch_status = request.data.get('status', 'PLANNING')

        if not anilist_id:
            return Response({'error': 'anilist_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Sync from AniList
            data = anilist_client.get_anime_detail(int(anilist_id))
            anime = sync_anime_from_anilist(data['Media'])

            # Create or update watchlist entry
            entry, created = WatchlistEntry.objects.update_or_create(
                user=request.user,
                anime=anime,
                defaults={'status': watch_status},
            )
            serializer = self.get_serializer(entry)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except AniListError:
            return Response({'error': 'AniList API error'}, status=status.HTTP_502_BAD_GATEWAY)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def increment_episode(self, request, pk=None):
        """POST /watchlist/{id}/increment_episode/ — +1 episodes_watched."""
        entry = self.get_object()
        max_episodes = entry.anime.episodes or 9999
        if entry.episodes_watched < max_episodes:
            entry.episodes_watched += 1
            entry.save()
        serializer = self.get_serializer(entry)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def decrement_episode(self, request, pk=None):
        """POST /watchlist/{id}/decrement_episode/ — -1 episodes_watched."""
        entry = self.get_object()
        if entry.episodes_watched > 0:
            entry.episodes_watched -= 1
            entry.save()
        serializer = self.get_serializer(entry)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_status(self, request):
        """GET /watchlist/by_status/?status=WATCHING"""
        status_param = request.query_params.get('status')
        queryset = self.get_queryset()
        if status_param:
            queryset = queryset.filter(status=status_param)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """GET /watchlist/stats/ — quick counts."""
        user = request.user
        qs = self.get_queryset()
        return Response({
            'watching': qs.filter(status=WatchlistEntry.Status.WATCHING).count(),
            'completed': qs.filter(status=WatchlistEntry.Status.COMPLETED).count(),
            'paused': qs.filter(status=WatchlistEntry.Status.PAUSED).count(),
            'dropped': qs.filter(status=WatchlistEntry.Status.DROPPED).count(),
            'planning': qs.filter(status=WatchlistEntry.Status.PLANNING).count(),
            'total': qs.count(),
        })
