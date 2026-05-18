from django.urls import path
from django.http import JsonResponse
from django.db import connection
from . import views


def health_check(request):
    try:
        connection.ensure_connection()
        db_ok = True
    except Exception:
        db_ok = False
    return JsonResponse({
        'status': 'ok' if db_ok else 'degraded',
        'db': 'ok' if db_ok else 'error',
        'service': 'anipulse',
    })


urlpatterns = [
    path('', views.home, name='home'),
    path('discover/', views.discover, name='discover'),
    path('anime/<int:anime_id>/', views.anime_detail, name='anime_detail'),
    path('anime/<int:anime_id>/review/', views.add_review, name='add_review'),
    path('review/<int:review_id>/like/', views.like_review, name='like_review'),
    path('anime/<int:anime_id>/discussions/', views.anime_discussions, name='anime_discussions'),
    path('discussions/<int:thread_id>/', views.discussion_thread, name='discussion_thread'),
    path('discussions/<int:thread_id>/comment/', views.add_comment, name='add_comment'),
    path('random/', views.random_anime, name='random_anime'),
    path('compare/', views.compare_anime, name='compare'),
    path('calendar/', views.calendar_view, name='calendar'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('watchlist/', views.watchlist_view, name='watchlist'),
    path('watchlist/add/', views.add_to_watchlist, name='add_to_watchlist'),
    path('watchlist/<int:entry_id>/update/', views.update_watchlist_entry, name='update_watchlist_entry'),
    path('notifications/', views.notification_settings, name='notification_settings'),
    path('notifications/json/', views.notifications_json, name='notifications_json'),
    path('notifications/<int:notif_id>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/read-all/', views.mark_all_read, name='mark_all_read'),
    path('settings/', views.user_settings, name='user_settings'),
    path('search/', views.search_view, name='search'),
    path('search/json/', views.search_json, name='search_json'),
    path('character/<int:character_id>/', views.character_view, name='character'),
    path('staff/<int:staff_id>/', views.staff_view, name='staff'),
    path('season/<int:year>/<str:season>/', views.seasonal_archive, name='seasonal_archive'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('profile/<str:username>/', views.profile_view, name='profile'),
    path('my-lists/', views.my_lists, name='my_lists'),
    path('lists/<int:list_id>/', views.view_list, name='view_list'),
    path('achievements/', views.achievements_view, name='achievements'),
    path('quiz/', views.quiz_view, name='quiz'),
    path('watch-time/', views.watch_time, name='watch_time'),
    path('recommendations/', views.recommendations_page, name='recommendations'),
    path('battles/', views.battle_list, name='battle_list'),
    path('battles/create/', views.battle_create, name='battle_create'),
    path('battles/<int:battle_id>/vote/', views.battle_vote, name='battle_vote'),
    path('tierlists/', views.tier_list_list, name='tier_list_list'),
    path('tierlists/create/', views.tier_list_create, name='tier_list_create'),
    path('tierlists/<slug:slug>/', views.tier_list_view, name='tier_list_view'),
    path('tierlists/<slug:slug>/add/', views.tier_list_add_item, name='tier_list_add_item'),
    path('social/', views.social_feed, name='social_feed'),
    path('social/post/', views.social_create_post, name='social_create_post'),
    path('social/like/<int:post_id>/', views.social_like_post, name='social_like_post'),
    path('social/follow/<str:username>/', views.social_follow, name='social_follow'),
    path('wrapped/', views.anime_wrapped, name='anime_wrapped'),
    path('quiz/personality/', views.personality_quiz, name='personality_quiz'),
    path('health/', health_check, name='health-check'),
    path('chat/', views.chat_ai, name='chat_ai'),
    path('sitemap.xml', views.sitemap_view, name='sitemap'),
    path('activity/', views.friend_activity, name='friend_activity'),
    path('import/', views.import_anilist, name='import_anilist'),
    path('watchlist/bulk-update/', views.bulk_update_watchlist, name='bulk_update_watchlist'),
    path('favorite/character/<int:character_id>/toggle/', views.toggle_character_favorite, name='toggle_character_favorite'),
    path('favorite/character/<int:character_id>/check/', views.check_character_favorite, name='check_character_favorite'),
    path('favorite/staff/<int:staff_id>/toggle/', views.toggle_staff_favorite, name='toggle_staff_favorite'),
    path('favorite/staff/<int:staff_id>/check/', views.check_staff_favorite, name='check_staff_favorite'),
]
