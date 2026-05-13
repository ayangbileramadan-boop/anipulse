from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AnimeViewSet, AnimeDetailAPIView

router = DefaultRouter()
router.register(r'', AnimeViewSet, basename='anime')

urlpatterns = [
    path('', include(router.urls)),
    path('detail/<int:pk>/', AnimeDetailAPIView.as_view({'get': 'retrieve'}), name='anime-detail'),
]
