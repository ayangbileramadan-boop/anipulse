from django.urls import path
from . import views_web

urlpatterns = [
    path('register/', views_web.register_view, name='register'),
]
