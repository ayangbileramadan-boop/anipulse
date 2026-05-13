from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'anime', views.AnimeViewSet, basename='api-anime')
router.register(r'watchlist', views.WatchlistEntryViewSet, basename='api-watchlist')
router.register(r'reviews', views.ReviewViewSet, basename='api-review')
router.register(r'discussions', views.DiscussionThreadViewSet, basename='api-discussion')
router.register(r'comments', views.DiscussionCommentViewSet, basename='api-comment')
router.register(r'lists', views.CustomListViewSet, basename='api-list')

urlpatterns = [
    path('', include(router.urls)),
    path('auth/', include('rest_framework.urls')),
]
