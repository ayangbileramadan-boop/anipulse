from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.anime.serializers import AnimeListSerializer
from .engine import get_recommendations_for_user


class RecommendationViewSet(viewsets.ViewSet):
    """
    Simple recommendation endpoint.
    Returns personalized anime recommendations based on user watch history.
    """
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'], url_path='for-me')
    def for_me(self, request):
        """GET /api/v1/recommendations/for-me/"""
        limit = min(int(request.query_params.get('limit', 12)), 50)
        anime_list = get_recommendations_for_user(request.user, limit=limit)
        serializer = AnimeListSerializer(anime_list, many=True)
        return Response({
            'count': len(serializer.data),
            'recommendations': serializer.data,
        })
