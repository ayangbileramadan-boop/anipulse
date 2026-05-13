from django.urls import path
from .views import (
    RegisterView, LoginView, LogoutView,
    MeView, ChangePasswordView, UserProfileView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('me/', MeView.as_view(), name='me'),
    path('me/change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('<str:username>/', UserProfileView.as_view(), name='user-profile'),
]
