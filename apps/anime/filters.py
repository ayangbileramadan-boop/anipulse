import django_filters
from .models import Anime


class AnimeFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(lookup_expr='iexact')
    format = django_filters.CharFilter(field_name='format', lookup_expr='iexact')
    season = django_filters.CharFilter(lookup_expr='iexact')
    season_year = django_filters.NumberFilter()
    min_score = django_filters.NumberFilter(field_name='average_score', lookup_expr='gte')
    max_score = django_filters.NumberFilter(field_name='average_score', lookup_expr='lte')
    genre = django_filters.CharFilter(field_name='genres__name', lookup_expr='iexact')

    class Meta:
        model = Anime
        fields = ['status', 'format', 'season', 'season_year']
