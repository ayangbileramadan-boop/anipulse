from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Q

from apps.anime.models import Anime, Review, DiscussionThread, DiscussionComment
from apps.watchlist.models import WatchlistEntry, CustomList
from .serializers import (
    AnimeListSerializer, AnimeDetailSerializer,
    WatchlistEntrySerializer, WatchlistEntryWriteSerializer,
    ReviewSerializer, DiscussionThreadSerializer,
    DiscussionCommentSerializer, CustomListSerializer,
)


class IsAuthenticatedForWrite(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user and request.user.is_authenticated


class IsOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.user == request.user


class AnimeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Anime.objects.select_related().prefetch_related('genres').all()
    filterset_fields = ['status', 'format', 'season', 'season_year']
    search_fields = ['title_romaji', 'title_english', 'title_native']
    ordering_fields = ['average_score', 'popularity', 'trending', 'season_year']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return AnimeDetailSerializer
        return AnimeListSerializer

    @action(detail=False)
    def trending(self, request):
        qs = self.get_queryset().filter(trending__isnull=False).order_by('-trending')[:30]
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False)
    def airing(self, request):
        qs = self.get_queryset().filter(status='RELEASING').order_by('-popularity')[:50]
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False)
    def top_rated(self, request):
        qs = self.get_queryset().filter(average_score__isnull=False).order_by('-average_score')[:50]
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False)
    def upcoming(self, request):
        qs = self.get_queryset().filter(status='NOT_YET_RELEASED').order_by('start_date')[:30]
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)


class WatchlistEntryViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    filterset_fields = ['status']
    ordering_fields = ['updated_at', 'score', 'started_at']

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return WatchlistEntryWriteSerializer
        return WatchlistEntrySerializer

    def get_queryset(self):
        return WatchlistEntry.objects.filter(user=self.request.user).select_related('anime')

    def perform_create(self, serializer):
        anilist_id = self.request.data.get('anilist_id') or self.kwargs.get('anilist_id')
        anime = Anime.objects.get(anilist_id=anilist_id)
        serializer.save(user=self.request.user, anime=anime)

    @action(detail=False)
    def stats(self, request):
        qs = self.get_queryset()
        return Response({
            'watching': qs.filter(status='WATCHING').count(),
            'completed': qs.filter(status='COMPLETED').count(),
            'planning': qs.filter(status='PLANNING').count(),
            'paused': qs.filter(status='PAUSED').count(),
            'dropped': qs.filter(status='DROPPED').count(),
            'total': qs.count(),
        })

    @action(detail=False)
    def currently_watching(self, request):
        qs = self.get_queryset().filter(status='WATCHING').order_by('-updated_at')[:10]
        serializer = WatchlistEntrySerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False)
    def recently_updated(self, request):
        qs = self.get_queryset().order_by('-updated_at')[:20]
        serializer = WatchlistEntrySerializer(qs, many=True)
        return Response(serializer.data)


class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.select_related('user', 'anime').all()
    permission_classes = [IsAuthenticatedForWrite, IsOwner]
    filterset_fields = ['anime', 'rating', 'is_spoiler']
    ordering_fields = ['created_at', 'likes', 'rating']

    def get_serializer_class(self):
        return ReviewSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def like(self, request, pk=None):
        review = self.get_object()
        review.likes += 1
        review.save(update_fields=['likes'])
        return Response({'likes': review.likes})


class DiscussionThreadViewSet(viewsets.ModelViewSet):
    queryset = DiscussionThread.objects.select_related('user', 'anime').annotate(
        comment_count=Count('comments')
    ).all()
    permission_classes = [IsAuthenticatedForWrite, IsOwner]
    filterset_fields = ['anime', 'episode_number', 'is_pinned', 'is_spoiler']
    ordering_fields = ['created_at', 'likes', 'views']

    def get_serializer_class(self):
        return DiscussionThreadSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class DiscussionCommentViewSet(viewsets.ModelViewSet):
    queryset = DiscussionComment.objects.select_related('user', 'thread').all()
    permission_classes = [IsAuthenticatedForWrite, IsOwner]
    filterset_fields = ['thread', 'parent']

    def get_serializer_class(self):
        return DiscussionCommentSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class CustomListViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsOwner]

    def get_serializer_class(self):
        return CustomListSerializer

    def get_queryset(self):
        return CustomList.objects.filter(user=self.request.user).annotate(
            item_count=Count('entries')
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
