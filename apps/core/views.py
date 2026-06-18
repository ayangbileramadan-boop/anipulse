import time
import logging
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from django.shortcuts import redirect, get_object_or_404
from apps.core.utils import safe_render as render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db import models, transaction
from django.db.models import Count, F, Q
from django.core.cache import cache
from django_ratelimit.decorators import ratelimit

from apps.anime.services.anilist import anilist_client, AniListError
from apps.anime.services.sync import sync_anime_from_anilist
from apps.watchlist.models import WatchlistEntry
from apps.watchlist.models import ACHIEVEMENT_DEFS
from apps.core.models import UserFollow, Streak
from apps.anime.models import Anime, Battle, BattleVote, TierList, TierListItem, TierListLike, SocialPost, SocialLike, UserActivity, Comment, CommentLike, FavoriteAnime
from apps.recommendations.engine import get_recommendations_for_user
from apps.core.services.personalization import PersonalizationEngine
from apps.core.services.gamification import GamificationEngine

logger = logging.getLogger(__name__)

GENRE_SPOTLIGHT = ['Action', 'Romance', 'Comedy', 'Fantasy', 'Sci-Fi', 'Slice of Life', 'Thriller', 'Sports', 'Mystery', 'Horror', 'Mecha', 'Music', 'Adventure', 'Drama', 'Supernatural', 'Psychology']


def home(request):
    trending = []
    airing = []
    popular = []
    top_rated = []
    upcoming = []
    genre_results = []
    spotlight_anime = None
    selected_genre = request.GET.get('genre', '')
    search_query = request.GET.get('search', '')
    selected_season = request.GET.get('season', '')
    selected_year = request.GET.get('year', '')

    try:
        trending_data = anilist_client.get_trending(page=1, per_page=30)
        trending = trending_data.get('Page', {}).get('media', [])
        if trending:
            spotlight_anime = trending[0]
    except AniListError as e:
        logger.error(f"Failed to fetch trending: {e}")

    try:
        now = int(time.time())
        end = now + (24 * 60 * 60)
        airing_data = anilist_client.get_airing_schedule(week_start=now, week_end=end)
        airing = [s for s in airing_data.get('Page', {}).get('airingSchedules', [])
                  if not s.get('media', {}).get('isAdult', False)]
    except AniListError as e:
        logger.error(f"Failed to fetch airing: {e}")

    try:
        now = datetime.now(timezone.utc)
        month = now.month
        year = now.year
        season = selected_season or {
            3: 'SPRING', 4: 'SPRING', 5: 'SPRING',
            6: 'SUMMER', 7: 'SUMMER', 8: 'SUMMER',
            9: 'FALL', 10: 'FALL', 11: 'FALL',
        }.get(month, 'WINTER')
        s_year = int(selected_year) if selected_year else year
        popular_data = anilist_client.get_popular_this_season(season=season, year=s_year, page=1, per_page=12)
        popular = popular_data.get('Page', {}).get('media', [])
    except AniListError as e:
        logger.error(f"Failed to fetch popular: {e}")

    try:
        top_rated_data = anilist_client.get_top_rated(page=1, per_page=10)
        top_rated = top_rated_data.get('Page', {}).get('media', [])
    except AniListError as e:
        logger.error(f"Failed to fetch top rated: {e}")

    try:
        upcoming_data = anilist_client.get_upcoming(page=1, per_page=10)
        upcoming = upcoming_data.get('Page', {}).get('media', [])
    except AniListError as e:
        logger.error(f"Failed to fetch upcoming: {e}")

    if selected_genre:
        try:
            genre_data = anilist_client.get_genre_anime(selected_genre, page=1, per_page=20)
            genre_results = genre_data.get('Page', {}).get('media', [])
        except AniListError as e:
            logger.error(f"Failed to fetch genre {selected_genre}: {e}")

    if search_query:
        try:
            search_data = anilist_client.search(search=search_query, page=1, per_page=20)
            search_results = search_data.get('Page', {}).get('media', [])
        except AniListError as e:
            logger.error(f"Failed to search {search_query}: {e}")
            search_results = []

    context = {
        'trending': trending,
        'airing': airing,
        'popular': popular,
        'top_rated': top_rated,
        'upcoming': upcoming,
        'spotlight_anime': spotlight_anime,
        'selected_genre': selected_genre,
        'genre_results': genre_results,
        'genre_spotlight': GENRE_SPOTLIGHT,
        'selected_season': selected_season,
    }

    if request.user.is_authenticated:
        try:
            context['recommendations'] = list(get_recommendations_for_user(request.user, limit=10))
        except Exception as e:
            logger.error(f"Failed to fetch recommendations: {e}")
        from apps.watchlist.models import WatchlistEntry
        context['currently_watching'] = WatchlistEntry.objects.filter(
            user=request.user, status='WATCHING'
        ).select_related('anime').order_by('-updated_at')[:8]
        context['stats'] = {
            'watching': WatchlistEntry.objects.filter(user=request.user, status='WATCHING').count(),
            'completed': WatchlistEntry.objects.filter(user=request.user, status='COMPLETED').count(),
            'planning': WatchlistEntry.objects.filter(user=request.user, status='PLANNING').count(),
        }
        try:
            engine = PersonalizationEngine()
            context['personalized_sections'] = engine.get_homepage_sections(request.user)
        except Exception as e:
            logger.error(f"Failed to generate personalized sections: {e}")
            context['personalized_sections'] = []

    if search_query:
        context['search_query'] = search_query
        context['search_results'] = search_results

    return render(request, 'home.html', context)


def discover(request):
    trending = []
    popular = []
    top_rated = []
    genre_results = []
    page_info = {}
    selected_genre = request.GET.get('genre', '')
    selected_mood = request.GET.get('mood', '')
    if selected_mood and not selected_genre:
        mood_map = {
            'action': 'Action', 'romance': 'Romance', 'psychological': 'Psychological',
            'comedy': 'Comedy', 'horror': 'Horror', 'sci-fi': 'Sci-Fi',
            'slice-of-life': 'Slice of Life', 'thriller': 'Thriller',
        }
        selected_genre = mood_map.get(selected_mood, '')
    search_query = request.GET.get('search', '')
    selected_season = request.GET.get('season', '')
    selected_year = request.GET.get('year', '')
    selected_format = request.GET.get('format', '')
    selected_status = request.GET.get('status', '')
    selected_sort = request.GET.get('sort', '')
    min_episodes = request.GET.get('min_episodes', '')
    max_episodes = request.GET.get('max_episodes', '')
    page = int(request.GET.get('page', 1))

    has_advanced_filters = any([selected_format, selected_status, selected_sort, min_episodes, max_episodes])

    if has_advanced_filters or selected_genre:
        sort_map = {
            'trending': ['TRENDING_DESC'],
            'score': ['SCORE_DESC'],
            'popularity': ['POPULARITY_DESC'],
            'favourites': ['FAVOURITES_DESC'],
            'newest': ['START_DATE_DESC'],
            'episodes': ['EPISODES_DESC'],
        }
        sort = sort_map.get(selected_sort, ['TRENDING_DESC'])
        try:
            search_data = anilist_client.search(
                search=search_query or None,
                genres=[selected_genre] if selected_genre else None,
                format=selected_format or None,
                status=selected_status or None,
                season=selected_season or None,
                year=int(selected_year) if selected_year else None,
                sort=sort,
                page=page, per_page=30,
            )
            search_results = search_data.get('Page', {}).get('media', [])
            page_info = search_data.get('Page', {}).get('pageInfo', {})
            genre_results = search_results
        except AniListError as e:
            logger.error(f"Failed to fetch filtered results: {e}")
            search_results = []
            genre_results = []
            page_info = {}
    else:
        search_results = []
        if search_query:
            try:
                search_data = anilist_client.search(search=search_query, page=page, per_page=20)
                search_results = search_data.get('Page', {}).get('media', [])
                page_info = search_data.get('Page', {}).get('pageInfo', {})
            except AniListError as e:
                logger.error(f"Failed to search {search_query}: {e}")

        try:
            trending_data = anilist_client.get_trending(page=1, per_page=30)
            trending = trending_data.get('Page', {}).get('media', [])
        except AniListError as e:
            logger.error(f"Failed to fetch trending: {e}")

        try:
            now = datetime.now(timezone.utc)
            month = now.month
            year = now.year
            season = selected_season or {
                3: 'SPRING', 4: 'SPRING', 5: 'SPRING',
                6: 'SUMMER', 7: 'SUMMER', 8: 'SUMMER',
                9: 'FALL', 10: 'FALL', 11: 'FALL',
            }.get(month, 'WINTER')
            s_year = int(selected_year) if selected_year else year
            popular_data = anilist_client.get_popular_this_season(season=season, year=s_year, page=1, per_page=12)
            popular = popular_data.get('Page', {}).get('media', [])
        except AniListError as e:
            logger.error(f"Failed to fetch popular: {e}")

        try:
            top_rated_data = anilist_client.get_top_rated(page=1, per_page=10)
            top_rated = top_rated_data.get('Page', {}).get('media', [])
        except AniListError as e:
            logger.error(f"Failed to fetch top rated: {e}")

        if selected_genre:
            try:
                genre_data = anilist_client.get_genre_anime(selected_genre, page=1, per_page=20)
                genre_results = genre_data.get('Page', {}).get('media', [])
            except AniListError as e:
                logger.error(f"Failed to fetch genre {selected_genre}: {e}")

    SEASONS = [
        ('WINTER', 'Winter'),
        ('SPRING', 'Spring'),
        ('SUMMER', 'Summer'),
        ('FALL', 'Fall'),
    ]
    FORMATS = [
        ('', 'All Formats'),
        ('TV', 'TV'),
        ('TV_SHORT', 'TV Short'),
        ('MOVIE', 'Movie'),
        ('SPECIAL', 'Special'),
        ('OVA', 'OVA'),
        ('ONA', 'ONA'),
        ('MUSIC', 'Music'),
    ]
    STATUSES = [
        ('', 'All Status'),
        ('FINISHED', 'Finished'),
        ('RELEASING', 'Airing'),
        ('NOT_YET_RELEASED', 'Not Yet Aired'),
        ('HIATUS', 'Hiatus'),
        ('CANCELLED', 'Cancelled'),
    ]
    SORT_OPTIONS = [
        ('', 'Trending'),
        ('score', 'Highest Rated'),
        ('popularity', 'Most Popular'),
        ('favourites', 'Most Favorited'),
        ('newest', 'Newest First'),
        ('episodes', 'Most Episodes'),
    ]
    context = {
        'trending': trending,
        'popular': popular,
        'top_rated': top_rated,
        'selected_genre': selected_genre,
        'genre_results': genre_results,
        'genre_spotlight': GENRE_SPOTLIGHT,
        'selected_season': selected_season,
        'search_query': search_query if search_query else '',
        'search_results': search_results,
        'seasons': SEASONS,
        'formats': FORMATS,
        'statuses': STATUSES,
        'sort_options': SORT_OPTIONS,
        'selected_format': selected_format,
        'selected_status': selected_status,
        'selected_sort': selected_sort,
        'selected_year': selected_year,
        'min_episodes': min_episodes,
        'max_episodes': max_episodes,
        'has_advanced_filters': has_advanced_filters,
        'page_info': page_info,
        'current_page': page,
    }
    return render(request, 'discover.html', context)


def anime_detail(request, anime_id):
    try:
        data = anilist_client.get_anime_detail(int(anime_id))
    except AniListError:
        return render(request, '404.html', status=404)

    media = data.get('Media', {})

    if request.GET.get('partial') == '1':
        from django.http import JsonResponse
        return JsonResponse({
            'id': media.get('id'),
            'title': media.get('title', {}),
            'coverImage': media.get('coverImage', {}),
            'format': media.get('format'),
            'averageScore': media.get('averageScore'),
        })
    title = media.get('title', {})
    title_english = title.get('english', '')
    title_romaji = title.get('romaji', '')
    title_native = title.get('native', '')

    start_date = ''
    if media.get('startDate', {}).get('year'):
        months = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        parts = []
        sd = media['startDate']
        if sd.get('month'):
            parts.append(months[sd['month']])
        if sd.get('day'):
            parts.append(str(sd['day']))
        if sd.get('year'):
            parts.append(str(sd['year']))
        start_date = ' '.join(parts)

    end_date = ''
    if media.get('endDate', {}).get('year'):
        ed = media['endDate']
        parts = []
        if ed.get('month'):
            parts.append(months[ed['month']])
        if ed.get('day'):
            parts.append(str(ed['day']))
        if ed.get('year'):
            parts.append(str(ed['year']))
        end_date = ' '.join(parts)

    next_airing_date = ''
    if media.get('nextAiringEpisode') and media['nextAiringEpisode'].get('airingAt'):
        ts = media['nextAiringEpisode']['airingAt']
        next_airing_date = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%b %d, %Y at %I:%M %p UTC')

    status_map = {
        'RELEASING': 'Currently Airing',
        'NOT_YET_RELEASED': 'Upcoming',
        'FINISHED': 'Finished',
        'CANCELLED': 'Cancelled',
        'HIATUS': 'On Hiatus',
    }

    characters = []
    edges = (media.get('characters') or {}).get('edges', [])
    for edge in edges:
        node = edge.get('node', {})
        vas = edge.get('voiceActors', [])
        characters.append({
            'id': node.get('id'),
            'name': node.get('name', {}).get('full', ''),
            'image': node.get('image', {}).get('medium', ''),
            'role': edge.get('role', ''),
            'voice_actors': [{
                'id': va.get('id'),
                'name': va.get('name', {}).get('full', ''),
                'image': va.get('image', {}).get('medium', ''),
                'language': va.get('languageV2', ''),
            } for va in vas],
        })

    from apps.anime.models import Review
    from apps.anime.forms import ReviewForm
    from apps.anime.services.sync import sync_anime_from_anilist

    try:
        local_anime = sync_anime_from_anilist(media)
        reviews = Review.objects.filter(anime=local_anime).select_related('user').order_by('-created_at')
        user_review = None
        if request.user.is_authenticated:
            user_review = Review.objects.filter(anime=local_anime, user=request.user).first()
    except Exception:
        reviews = []
        user_review = None
        local_anime = None

    trailer = None
    trailer_data = media.get('trailer')
    if trailer_data and trailer_data.get('id') and trailer_data.get('site'):
        vid_id = trailer_data['id'].strip()
        site = trailer_data['site'].strip().lower()
        if site == 'youtube' and len(vid_id) == 11:
            trailer = {
                'id': vid_id,
                'embed_url': f'https://www.youtube.com/embed/{vid_id}',
                'watch_url': f'https://www.youtube.com/watch?v={vid_id}',
                'thumbnail': trailer_data.get('thumbnail', ''),
            }
    elif local_anime and local_anime.trailer_id and local_anime.trailer_site:
        vid_id = local_anime.trailer_id.strip()
        site = local_anime.trailer_site.strip().lower()
        if site == 'youtube' and len(vid_id) == 11:
            trailer = {
                'id': vid_id,
                'embed_url': f'https://www.youtube.com/embed/{vid_id}',
                'watch_url': f'https://www.youtube.com/watch?v={vid_id}',
                'thumbnail': local_anime.trailer_thumbnail,
            }

    external_links = media.get('externalLinks', [])
    streaming_links = [l for l in external_links if l.get('url') and l.get('site') not in ('AniList', 'MyAnimeList', 'Wikipedia', 'Reddit', 'Twitter')]
    info_links = [l for l in external_links if l.get('site') in ('MyAnimeList', 'AniDB', 'Wikipedia')]

    stats = {
        'score_distribution': _get_score_distribution(media),
        'rank_info': _get_rank_info(media),
    }

    search_title = (title_english or title_romaji or '').strip()
    from urllib.parse import quote
    animepahe_base = getattr(settings, 'ANIMEPAHE_BASE_URL', 'https://animepahe.pw')
    animepahe_url = ''
    if search_title:
        try:
            import requests
            api_url = f'{animepahe_base}/api?m=search&q={quote(search_title)}'
            resp = requests.get(api_url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                entries = data.get('data', [])
                if entries:
                    session = entries[0].get('session')
                    if session:
                        animepahe_url = f'{animepahe_base}/anime/{session}'
        except Exception:
            pass
        if not animepahe_url:
            animepahe_url = f'{animepahe_base}?q={quote(search_title)}'

    # Fetch AniList reviews
    anilist_reviews = []
    try:
        reviews_data = anilist_client.get_media_reviews(int(anime_id))
        anilist_reviews = reviews_data.get('Media', {}).get('reviews', {}).get('nodes', [])
    except AniListError as e:
        logger.error(f"Failed to fetch AniList reviews: {e}")

    # Fetch local theme songs
    themes = local_anime.themes.all() if local_anime else []

    return render(request, 'anime_detail.html', {
        'anilist_id': anime_id,
        'title': title_english or title_romaji,
        'title_native': title_native,
        'cover': media.get('coverImage', {}).get('large', '') or media.get('coverImage', {}).get('medium', ''),
        'cover_color': media.get('coverImage', {}).get('color', '#1a1a2e'),
        'banner': media.get('bannerImage', ''),
        'description': media.get('description', ''),
        'format': media.get('format', ''),
        'status': media.get('status', ''),
        'status_label': status_map.get(media.get('status', ''), media.get('status', '')),
        'episodes': media.get('episodes'),
        'duration': media.get('duration'),
        'season': media.get('season', ''),
        'season_year': media.get('seasonYear'),
        'start_date': start_date,
        'end_date': end_date,
        'average_score': media.get('averageScore'),
        'mean_score': media.get('meanScore'),
        'popularity': media.get('popularity'),
        'favourites': media.get('favourites'),
        'trending': media.get('trending'),
        'genres': media.get('genres', []),
        'studios': (media.get('studios') or {}).get('nodes', []),
        'tags': media.get('tags', []),
        'relations': (media.get('relations') or {}).get('edges', []),
        'recommendations': media.get('recommendations', {}).get('nodes', []),
        'site_url': media.get('siteUrl', ''),
        'next_airing_episode': media.get('nextAiringEpisode'),
        'next_airing_date': next_airing_date,
        'characters': characters,
        'trailer': trailer,
        'streaming_links': streaming_links,
        'info_links': info_links,
        'stats': stats,
        'reviews': reviews,
        'user_review': user_review,
        'animepahe_url': animepahe_url,
        'anilist_reviews': anilist_reviews,
        'romaji_title': title_romaji,
        'themes': themes,
        'isAdult': media.get('isAdult', False),
    })


def _get_score_distribution(media):
    avg = media.get('averageScore')
    if not avg:
        return None
    score = avg / 10
    if score >= 8.5:
        return {'label': 'Masterpiece', 'color': '#22c55e', 'pct': 95}
    elif score >= 7.5:
        return {'label': 'Great', 'color': '#3b82f6', 'pct': 80}
    elif score >= 6.5:
        return {'label': 'Good', 'color': '#eab308', 'pct': 65}
    elif score >= 5.5:
        return {'label': 'Average', 'color': '#f97316', 'pct': 50}
    else:
        return {'label': 'Below Average', 'color': '#ef4444', 'pct': 35}


def _get_rank_info(media):
    popularity = media.get('popularity', 0)
    favourites = media.get('favourites', 0)
    if popularity > 100000:
        pop_label = 'Legendary'
    elif popularity > 50000:
        pop_label = 'Very Popular'
    elif popularity > 20000:
        pop_label = 'Popular'
    else:
        pop_label = 'Niche'
    return {'popularity_label': pop_label, 'popularity': popularity, 'favourites': favourites}


def calendar_view(request):
    try:
        now = int(time.time())
        week_end = now + (7 * 24 * 60 * 60)
        data = anilist_client.get_airing_schedule(week_start=now, week_end=week_end)
        schedules = [s for s in data.get('Page', {}).get('airingSchedules', [])
                     if not s.get('media', {}).get('isAdult', False)]
    except AniListError:
        schedules = []

    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    days = []

    for i, name in enumerate(day_names):
        day_entries = []
        for s in schedules:
            dt = datetime.fromtimestamp(s['airingAt'], tz=timezone.utc)
            if dt.weekday() == i:
                s['airing_time'] = dt
                day_entries.append(s)
        day_entries.sort(key=lambda x: x['airingAt'])
        days.append({'name': name, 'entries': day_entries})

    return render(request, 'calendar.html', {'days': days})


@login_required
def dashboard_view(request):
    stats = {
        'watching': WatchlistEntry.objects.filter(user=request.user, status='WATCHING').count(),
        'completed': WatchlistEntry.objects.filter(user=request.user, status='COMPLETED').count(),
        'paused': WatchlistEntry.objects.filter(user=request.user, status='PAUSED').count(),
        'dropped': WatchlistEntry.objects.filter(user=request.user, status='DROPPED').count(),
        'planning': WatchlistEntry.objects.filter(user=request.user, status='PLANNING').count(),
        'total': WatchlistEntry.objects.filter(user=request.user).count(),
    }

    genre_counts = {}
    for entry in WatchlistEntry.objects.filter(user=request.user, status__in=['WATCHING', 'COMPLETED']).select_related('anime').prefetch_related('anime__genres'):
        for g in entry.anime.genres.all():
            genre_counts[g.name] = genre_counts.get(g.name, 0) + 1
    genre_chart = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:8]

    score_counts = [0] * 10
    scored_entries = WatchlistEntry.objects.filter(user=request.user, score__isnull=False).exclude(score=0)
    for entry in scored_entries:
        if 1 <= entry.score <= 10:
            score_counts[entry.score - 1] += 1

    recent_entries = WatchlistEntry.objects.filter(
        user=request.user
    ).select_related('anime').order_by('-updated_at')[:10]

    currently_watching = WatchlistEntry.objects.filter(
        user=request.user, status='WATCHING'
    ).select_related('anime').order_by('-updated_at')[:5]

    recommendations = []
    if stats['total'] > 0:
        try:
            recommendations = list(get_recommendations_for_user(request.user, limit=8))
        except Exception as e:
            logger.error(f"Failed to fetch recommendations: {e}")

    try:
        now = int(time.time())
        end = now + (7 * 24 * 60 * 60)
        airing_data = anilist_client.get_airing_schedule(week_start=now, week_end=end)
        airing_schedules = airing_data.get('Page', {}).get('airingSchedules', [])
        my_anime_ids = set(
            WatchlistEntry.objects.filter(
                user=request.user, status__in=['WATCHING', 'PLANNING']
            ).values_list('anime__anilist_id', flat=True)
        )
        my_airing = [
            s for s in airing_schedules
            if s.get('media', {}).get('id') in my_anime_ids
        ][:5]
    except AniListError:
        my_airing = []

    return render(request, 'dashboard.html', {
        'stats': stats,
        'recent_entries': recent_entries,
        'currently_watching': currently_watching,
        'recommendations': recommendations,
        'my_airing': my_airing,
        'genre_chart': genre_chart,
        'score_chart': score_counts,
    })


@login_required
@transaction.atomic
def update_watchlist_entry(request, entry_id):
    entry = get_object_or_404(WatchlistEntry, id=entry_id, user=request.user)
    if request.method == 'POST':
        status = request.POST.get('status')
        if status and status in dict(WatchlistEntry.Status.choices):
            entry.status = status
        eps = request.POST.get('episodes_watched')
        if eps is not None and eps != '':
            entry.episodes_watched = max(0, int(eps))
        score = request.POST.get('score')
        if score is not None and score != '':
            try:
                entry.score = max(0, min(10, float(score)))
            except ValueError:
                pass
        entry.save()
    return redirect(request.META.get('HTTP_REFERER', 'watchlist'))


@login_required
def watchlist_view(request):
    status_filter = request.GET.get('status', '')
    qs = WatchlistEntry.objects.filter(user=request.user).select_related('anime')

    if status_filter:
        qs = qs.filter(status=status_filter)

    paginator = Paginator(qs.order_by('-updated_at'), 20)
    page = request.GET.get('page', 1)
    entries = paginator.get_page(page)

    stats = {
        'watching': WatchlistEntry.objects.filter(user=request.user, status='WATCHING').count(),
        'completed': WatchlistEntry.objects.filter(user=request.user, status='COMPLETED').count(),
        'paused': WatchlistEntry.objects.filter(user=request.user, status='PAUSED').count(),
        'dropped': WatchlistEntry.objects.filter(user=request.user, status='DROPPED').count(),
        'planning': WatchlistEntry.objects.filter(user=request.user, status='PLANNING').count(),
        'total': WatchlistEntry.objects.filter(user=request.user).count(),
    }

    return render(request, 'watchlist.html', {
        'entries': entries,
        'stats': stats,
        'status_filter': status_filter,
        'STATUS_CHOICES': WatchlistEntry.Status.choices,
    })


@login_required
@transaction.atomic
def add_to_watchlist(request):
    if request.method == 'POST':
        anilist_id = request.POST.get('anilist_id')
        status = request.POST.get('status', 'PLANNING')

        if not anilist_id:
            messages.error(request, 'Missing anime ID.')
            return redirect(request.META.get('HTTP_REFERER', '/'))

        try:
            data = anilist_client.get_anime_detail(int(anilist_id))
            anime = sync_anime_from_anilist(data['Media'])

            entry, created = WatchlistEntry.objects.update_or_create(
                user=request.user,
                anime=anime,
                defaults={'status': status},
            )
            if created:
                messages.success(request, 'Added to your watchlist!')
            else:
                messages.info(request, 'Updated watchlist status.')
        except AniListError:
            messages.error(request, 'Failed to fetch anime data.')
        except Exception as e:
            messages.error(request, str(e))

    return redirect(request.META.get('HTTP_REFERER', '/'))


@login_required
@transaction.atomic
def notification_settings(request):
    user = request.user
    if request.method == 'POST':
        user.notify_new_episodes = request.POST.get('notify_new_episodes') == 'on'
        user.notify_airing = request.POST.get('notify_airing') == 'on'
        user.timezone = request.POST.get('timezone', 'UTC')
        user.save()
        messages.success(request, 'Notification settings updated!')
        return redirect('notification_settings')

    return render(request, 'notification_settings.html', {'user': user})


def my_profile_redirect(request):
    from django.shortcuts import redirect
    if not request.user.is_authenticated:
        return redirect('login')
    return redirect('profile', username=request.user.username)


def profile_view(request, username):
    User = get_user_model()
    profile_user = get_object_or_404(User, username=username)
    is_me = request.user == profile_user if request.user.is_authenticated else False
    is_following = False
    if request.user.is_authenticated and not is_me:
        is_following = UserFollow.objects.filter(follower=request.user, following=profile_user).exists()

    show_watchlist = is_me or profile_user.is_watchlist_public

    stats = {'watching': 0, 'completed': 0, 'paused': 0, 'dropped': 0, 'planning': 0, 'total': 0}
    total_hours = 0
    currently_watching = []
    recently_completed = []
    favorite_anime_list = []

    if show_watchlist:
        stats_qs = WatchlistEntry.objects.filter(user=profile_user).values('status').annotate(cnt=models.Count('id'))
        stats = {s['status']: s['cnt'] for s in stats_qs}
        stats.setdefault('total', sum(stats.values()))

        total_hours = WatchlistEntry.objects.filter(
            user=profile_user, status__in=['COMPLETED', 'WATCHING']
        ).select_related('anime').annotate(
            watched_ep=models.Case(
                models.When(status='WATCHING', then=models.F('episodes_watched')),
                default=models.F('anime__episodes'),
                output_field=models.IntegerField(),
            )
        ).aggregate(
            total=models.Sum(models.F('watched_ep') * models.F('anime__duration'), output_field=models.FloatField())
        )['total'] or 0
        total_hours = round(total_hours / 60, 1)

        currently_watching = WatchlistEntry.objects.filter(
            user=profile_user, status='WATCHING'
        ).select_related('anime').order_by('-updated_at')[:6]

        recently_completed = WatchlistEntry.objects.filter(
            user=profile_user, status='COMPLETED'
        ).select_related('anime').order_by('-updated_at')[:6]

    favorite_anime_list = FavoriteAnime.objects.filter(
        user=profile_user
    ).select_related('anime').order_by('-created_at')[:6]

    tier_lists = TierList.objects.filter(
        user=profile_user, is_public=True
    ).prefetch_related('items')[:6]

    recent_activity = UserActivity.objects.filter(
        user=profile_user
    ).select_related('anime').order_by('-created_at')[:10]

    follower_count = UserFollow.objects.filter(following=profile_user).count()
    following_count = UserFollow.objects.filter(follower=profile_user).count()

    streak = Streak.objects.filter(user=profile_user).first()

    game_engine = GamificationEngine()
    game_profile = game_engine.get_profile(profile_user)
    level_progress = game_profile.level_progress
    unlocked_badges = game_engine.get_unlocked_badges(profile_user)

    return render(request, 'profile.html', {
        'profile_user': profile_user,
        'is_me': is_me,
        'is_following': is_following,
        'show_watchlist': show_watchlist,
        'stats': stats,
        'total_watch_hours': total_hours,
        'profile_streak': streak,
        'game_profile': game_profile,
        'level_progress': level_progress,
        'unlocked_badges': unlocked_badges,
        'currently_watching': currently_watching,
        'recently_completed': recently_completed,
        'favorite_anime_list': favorite_anime_list,
        'tier_lists': tier_lists,
        'recent_activity': recent_activity,
        'follower_count': follower_count,
        'following_count': following_count,
    })


@login_required
@transaction.atomic
def profile_follow_json(request, username):
    from django.http import JsonResponse
    User = get_user_model()
    target = get_object_or_404(User, username=username)
    if target == request.user:
        return JsonResponse({'error': 'Cannot follow yourself'}, status=400)
    follow, created = UserFollow.objects.get_or_create(follower=request.user, following=target)
    if not created:
        follow.delete()
        return JsonResponse({'following': False, 'followers': UserFollow.objects.filter(following=target).count()})
    _create_notification(target, f'{request.user.username} started following you', url=f'/profile/{request.user.username}/', ntype='FOLLOW')
    return JsonResponse({'following': True, 'followers': UserFollow.objects.filter(following=target).count()})


def profile_followers(request, username):
    User = get_user_model()
    profile_user = get_object_or_404(User, username=username)
    followers_qs = UserFollow.objects.filter(following=profile_user).select_related('follower').order_by('-created_at')
    paginator = Paginator(followers_qs, 20)
    page = request.GET.get('page', 1)
    followers = paginator.get_page(page)
    return render(request, 'profile_follow_list.html', {
        'profile_user': profile_user,
        'users': followers,
        'list_type': 'followers',
    })


def profile_following(request, username):
    User = get_user_model()
    profile_user = get_object_or_404(User, username=username)
    following_qs = UserFollow.objects.filter(follower=profile_user).select_related('following').order_by('-created_at')
    paginator = Paginator(following_qs, 20)
    page = request.GET.get('page', 1)
    following = paginator.get_page(page)
    return render(request, 'profile_follow_list.html', {
        'profile_user': profile_user,
        'users': following,
        'list_type': 'following',
    })


@login_required
@transaction.atomic
def add_review(request, anime_id):
    from apps.anime.models import Anime, Review
    from apps.anime.forms import ReviewForm
    from apps.anime.services.anilist import anilist_client, AniListError
    from apps.anime.services.sync import sync_anime_from_anilist

    try:
        anime = Anime.objects.get(anilist_id=anime_id)
    except Anime.DoesNotExist:
        try:
            data = anilist_client.get_anime_detail(anime_id)
            if data.get('Media'):
                anime = sync_anime_from_anilist(data['Media'])
            else:
                return redirect('home')
        except AniListError:
            return redirect('home')

    if Review.objects.filter(anime=anime, user=request.user).exists():
        messages.info(request, 'You already reviewed this anime.')
        return redirect('anime_detail', anime_id=anime_id)

    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.anime = anime
            review.user = request.user
            review.save()
            _check_achievements(request.user)
            messages.success(request, 'Review posted!')
            return redirect('anime_detail', anime_id=anime_id)
    else:
        form = ReviewForm()

    return render(request, 'add_review.html', {'form': form, 'anime': anime})


@login_required
@transaction.atomic
def like_review(request, review_id):
    from apps.anime.models import Review
    review = get_object_or_404(Review, id=review_id)
    if review.user != request.user:
        Review.objects.filter(id=review.id).update(likes=F('likes') + 1)
        _create_notification(review.user, f'{request.user.username} liked your review',
                             url=f'/anime/{review.anime.anilist_id}/', ntype='LIKE')
        UserActivity.objects.create(
            user=request.user,
            activity_type='LIKE',
            description='Liked a review',
        )
    return redirect('anime_detail', anime_id=review.anime.anilist_id)


def random_anime(request):
    from apps.anime.services.anilist import anilist_client, AniListError
    import random

    try:
        page = random.randint(1, 20)
        data = anilist_client.search(page=page, per_page=10)
        media = data.get('Page', {}).get('media', [])
        if media:
            anime = random.choice(media)
            return redirect('anime_detail', anime_id=anime['id'])
    except Exception:
        pass
    return redirect('home')


def compare_anime(request):
    from apps.anime.services.anilist import anilist_client, AniListError

    id1 = request.GET.get('id1', '')
    id2 = request.GET.get('id2', '')
    data1 = {}
    data2 = {}

    if id1:
        try:
            result = anilist_client.get_anime_detail(int(id1))
            data1 = result.get('Media', {}) or {}
        except (AniListError, ValueError, TypeError, AttributeError):
            data1 = {}

    if id2:
        try:
            result = anilist_client.get_anime_detail(int(id2))
            data2 = result.get('Media', {}) or {}
        except (AniListError, ValueError, TypeError, AttributeError):
            data2 = {}

    if request.GET.get('partial') == '1':
        return render(request, 'compare_partial.html', {
            'data1': data1,
            'data2': data2,
            'id1': id1,
            'id2': id2,
        })

    return render(request, 'compare.html', {
        'data1': data1,
        'data2': data2,
        'id1': id1,
        'id2': id2,
    })


@login_required
@transaction.atomic
def profile_edit(request):
    from PIL import Image
    from apps.core.utils import validate_uploaded_image

    logger = logging.getLogger(__name__)
    user = request.user
    ok = True
    if request.method == 'POST':
        user.bio = request.POST.get('bio', '')

        if 'avatar_file' in request.FILES:
            f = request.FILES['avatar_file']
            err = validate_uploaded_image(f)
            if err:
                messages.error(request, err)
                ok = False
            else:
                old_name = user.avatar.name if user.avatar and user.avatar.name else None
                try:
                    img = Image.open(f)
                    img.verify()
                    f.seek(0)
                    user.avatar.save(f'avatar_{uuid4().hex}', f)
                except Exception as exc:
                    logger.exception('Avatar upload failed: %s | content_type=%s | size=%s',
                                     exc, getattr(f, 'content_type', '?'), getattr(f, 'size', '?'))
                    messages.error(request, 'Failed to upload avatar.')
                    ok = False
                else:
                    if old_name:
                        try:
                            user.avatar.storage.delete(old_name)
                        except Exception:
                            logger.warning('Failed to delete old avatar: %s', old_name)

        if 'cover_file' in request.FILES:
            f = request.FILES['cover_file']
            err = validate_uploaded_image(f)
            if err:
                messages.error(request, err)
                ok = False
            else:
                old_name = user.cover_image.name if user.cover_image and user.cover_image.name else None
                try:
                    img = Image.open(f)
                    img.verify()
                    f.seek(0)
                    user.cover_image.save(f'cover_{uuid4().hex}', f)
                except Exception as exc:
                    logger.exception('Cover upload failed: %s | content_type=%s | size=%s',
                                     exc, getattr(f, 'content_type', '?'), getattr(f, 'size', '?'))
                    messages.error(request, 'Failed to upload cover image.')
                    ok = False
                else:
                    if old_name:
                        try:
                            user.cover_image.storage.delete(old_name)
                        except Exception:
                            logger.warning('Failed to delete old cover: %s', old_name)

        if 'remove_avatar' in request.POST:
            user.avatar.delete(save=False)
            user.avatar = None

        if 'remove_cover' in request.POST:
            user.cover_image.delete(save=False)
            user.cover_image = None

        user.save()
        if ok:
            messages.success(request, 'Profile updated!')
        return redirect('profile', username=user.username)
    return render(request, 'profile_edit.html', {'user': user})


@login_required
@transaction.atomic
def my_lists(request):
    from apps.watchlist.models import CustomList
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            name = request.POST.get('name', '').strip()
            if name:
                cl, created = CustomList.objects.get_or_create(user=request.user, name=name)
                if created:
                    cl.description = request.POST.get('description', '')
                    cl.is_public = request.POST.get('is_public') == 'on'
                    cl.save()
                    _check_achievements(request.user)
                    messages.success(request, f'List "{name}" created!')
        elif action == 'delete':
            list_id = request.POST.get('list_id')
            CustomList.objects.filter(id=list_id, user=request.user).delete()
        elif action == 'add_anime':
            list_id = request.POST.get('list_id')
            anilist_id = request.POST.get('anilist_id')
            try:
                anime = Anime.objects.get(anilist_id=anilist_id)
                cl = CustomList.objects.get(id=list_id, user=request.user)
                cl.anime.add(anime)
            except (Anime.DoesNotExist, CustomList.DoesNotExist):
                pass
        elif action == 'remove_anime':
            list_id = request.POST.get('list_id')
            anime_id = request.POST.get('anime_id')
            try:
                cl = CustomList.objects.get(id=list_id, user=request.user)
                cl.anime.remove(anime_id)
            except CustomList.DoesNotExist:
                pass
        return redirect('my_lists')

    lists = CustomList.objects.filter(user=request.user).prefetch_related('anime').order_by('-updated_at')
    return render(request, 'my_lists.html', {'custom_lists': lists})


@login_required
def view_list(request, list_id):
    from apps.watchlist.models import CustomList
    cl = get_object_or_404(CustomList, id=list_id)
    if not cl.is_public and cl.user != request.user:
        return redirect('home')
    return render(request, 'view_list.html', {'custom_list': cl})


def achievements_view(request):
    from apps.watchlist.models import Achievement
    if not request.user.is_authenticated:
        return redirect('login')
    unlocked = Achievement.objects.filter(user=request.user)
    unlocked_keys = set(a.key for a in unlocked)
    available = []
    for key, defs in ACHIEVEMENT_DEFS.items():
        if key not in unlocked_keys:
            available.append({'key': key, **defs})
    return render(request, 'achievements.html', {
        'unlocked': unlocked,
        'available': available,
    })


def quiz_view(request):
    from apps.anime.services.anilist import anilist_client
    import random

    if request.method == 'POST':
        score = int(request.POST.get('score', 0))
        total = int(request.POST.get('total', 0))
        if total >= 5:
            _check_achievements(request.user)
            if score == total:
                messages.success(request, f'Perfect score! {score}/{total} 🎉')
            else:
                messages.info(request, f'Score: {score}/{total}')
        return redirect('quiz')

    try:
        trending = anilist_client.get_trending(page=1, per_page=20)
        all_media = trending.get('Page', {}).get('media', [])
        if len(all_media) < 8:
            messages.warning(request, 'Not enough anime loaded for quiz. Try again later.')
            return redirect('home')

        random.shuffle(all_media)
        questions = []
        for i in range(min(10, len(all_media))):
            correct = all_media[i]
            others = [m for m in all_media if m['id'] != correct['id']]
            random.shuffle(others)
            options = [correct] + others[:3]
            random.shuffle(options)
            questions.append({
                'id': correct['id'],
                'image': correct.get('coverImage', {}).get('medium', ''),
                'options': options,
            })

        return render(request, 'quiz.html', {'questions': questions})
    except Exception as e:
        messages.error(request, f'Failed to load quiz: {e}')
        return redirect('home')


def battle_list(request):
    cached = cache.get('battle_list_data')
    if cached is not None:
        return render(request, 'battles.html', cached)

    from django.utils import timezone
    now = timezone.now()

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    has_daily = Battle.objects.filter(is_daily_featured=True, created_at__gte=today_start).exists()
    if not has_daily:
        try:
            from apps.anime.models import Anime
            top = Anime.objects.filter(average_score__isnull=False).exclude(average_score=0).order_by('-popularity')[:10]
            if len(top) >= 4:
                import random
                shuffled = list(top)
                random.shuffle(shuffled)
                pairs = [(shuffled[i], shuffled[i+1]) for i in range(0, len(shuffled)-1, 2)]
                for a1, a2 in pairs[:2]:
                    _, created = Battle.objects.get_or_create(
                        anime1=a1, anime2=a2, is_daily_featured=True,
                        defaults={
                            'is_active': True,
                            'category': 'versus',
                            'expires_at': now + timedelta(days=1),
                        },
                    )
        except Exception:
            pass

    active_qs = Battle.objects.filter(
        is_active=True,
    ).filter(
        expires_at__isnull=True
    ) | Battle.objects.filter(
        is_active=True,
        expires_at__gte=now,
    )
    active_qs = active_qs.select_related('anime1', 'anime2', 'created_by')

    if not active_qs.exists():
        try:
            from django.core.management import call_command
            call_command('seed_battles')
            active_qs = Battle.objects.filter(is_active=True).select_related('anime1', 'anime2', 'created_by')
        except Exception:
            pass

    trending = list(active_qs.annotate(total=F('votes1') + F('votes2')).order_by('-total')[:3])
    paginator = Paginator(active_qs, 20)
    page_number = request.GET.get('page', 1)
    battles = paginator.get_page(page_number)

    user_votes = {}
    if request.user.is_authenticated:
        user_votes = dict(
            BattleVote.objects.filter(
                battle__in=[b.id for b in battles],
                user=request.user,
            ).values_list('battle_id', 'choice')
        )

    context = {
        'battles': battles,
        'trending': trending,
        'total_battles': active_qs.count(),
        'user_votes': user_votes,
    }
    return render(request, 'battles.html', context)


@login_required
def battle_create(request):
    if request.method == 'POST':
        a1 = request.POST.get('anime1', '').strip()
        a2 = request.POST.get('anime2', '').strip()
        cat = request.POST.get('category', 'versus')
        if a1 and a2:
            results = []
            for q in [a1, a2]:
                try:
                    data = anilist_client.search(search=q, page=1, per_page=1)
                    media = data.get('Page', {}).get('media', [])
                    if media:
                        sync_anime_from_anilist(media[0])
                        results.append(Anime.objects.filter(anilist_id=media[0]['id']).first())
                except AniListError:
                    results.append(None)
            if results[0] and results[1]:
                battle = Battle.objects.create(
                    anime1=results[0], anime2=results[1],
                    created_by=request.user, category=cat,
                )
                UserActivity.objects.create(
                    user=request.user, activity_type='BATTLE',
                    description=f'Created battle: {battle.anime1} vs {battle.anime2}',
                )
                messages.success(request, 'Battle created!')
                return redirect('battle_list')
        messages.error(request, 'Could not create battle. Try searching exact titles.')
    return render(request, 'battle_create.html')


@login_required
@transaction.atomic
def battle_vote(request, battle_id):
    battle = get_object_or_404(
        Battle.objects.select_for_update().filter(
            is_active=True,
        ).filter(
            expires_at__isnull=True
        ) | Battle.objects.select_for_update().filter(
            is_active=True, expires_at__gte=timezone.now()
        ),
        id=battle_id,
    )
    if request.method == 'POST':
        choice = request.POST.get('choice')
        if choice in ('1', '2'):
            choice = int(choice)
            vote, created = BattleVote.objects.get_or_create(
                battle=battle, user=request.user,
                defaults={'choice': choice},
            )
            if not created:
                old_choice = vote.choice
                if old_choice != choice:
                    vote.choice = choice
                    vote.save(update_fields=['choice'])
                    if old_choice == 1:
                        Battle.objects.filter(id=battle.id).update(votes1=F('votes1') - 1)
                    else:
                        Battle.objects.filter(id=battle.id).update(votes2=F('votes2') - 1)
                    if choice == 1:
                        Battle.objects.filter(id=battle.id).update(votes1=F('votes1') + 1)
                    else:
                        Battle.objects.filter(id=battle.id).update(votes2=F('votes2') + 1)
            else:
                if choice == 1:
                    Battle.objects.filter(id=battle.id).update(votes1=F('votes1') + 1)
                else:
                    Battle.objects.filter(id=battle.id).update(votes2=F('votes2') + 1)
                UserActivity.objects.create(
                    user=request.user, activity_type='BATTLE',
                    description=f"Voted in {battle}",
                )
            if created and battle.created_by and battle.created_by != request.user:
                _create_notification(battle.created_by, f'{request.user.username} voted in your battle "{battle.title}"' if battle.title else f'{request.user.username} voted in a battle', url=f'/battles/{battle.id}/', ntype='BATTLE_VOTE')
            battle.refresh_from_db()
    return redirect('battle_list')


@login_required
def battle_vote_json(request, battle_id):
    from django.http import JsonResponse
    battle = get_object_or_404(Battle, id=battle_id, is_active=True)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    choice = request.POST.get('choice')
    if choice not in ('1', '2'):
        return JsonResponse({'error': 'Invalid choice'}, status=400)
    choice = int(choice)

    with transaction.atomic():
        battle = Battle.objects.select_for_update().get(id=battle_id)
        vote, created = BattleVote.objects.get_or_create(
            battle=battle, user=request.user,
            defaults={'choice': choice},
        )
        if not created:
            old_choice = vote.choice
            if old_choice != choice:
                vote.choice = choice
                vote.save(update_fields=['choice'])
                if old_choice == 1:
                    Battle.objects.filter(id=battle.id).update(votes1=F('votes1') - 1)
                else:
                    Battle.objects.filter(id=battle.id).update(votes2=F('votes2') - 1)
                if choice == 1:
                    Battle.objects.filter(id=battle.id).update(votes1=F('votes1') + 1)
                else:
                    Battle.objects.filter(id=battle.id).update(votes2=F('votes2') + 1)
        else:
            if choice == 1:
                Battle.objects.filter(id=battle.id).update(votes1=F('votes1') + 1)
            else:
                Battle.objects.filter(id=battle.id).update(votes2=F('votes2') + 1)
                UserActivity.objects.create(
                    user=request.user, activity_type='BATTLE',
                    description=f"Voted in {battle}",
                )
            if created and battle.created_by and battle.created_by != request.user:
                _create_notification(battle.created_by, f'{request.user.username} voted in your battle "{battle.title}"' if battle.title else f'{request.user.username} voted in a battle', url=f'/battles/{battle.id}/', ntype='BATTLE_VOTE')
            battle.refresh_from_db()

    return JsonResponse({
        'votes1': battle.votes1,
        'votes2': battle.votes2,
        'total': battle.total_votes,
        'pct1': battle.pct1,
        'pct2': battle.pct2,
        'choice': choice,
        'liked': True,
    })


def battle_data_json(request, battle_id):
    from django.http import JsonResponse
    battle = get_object_or_404(Battle, id=battle_id, is_active=True)
    return JsonResponse({
        'votes1': battle.votes1,
        'votes2': battle.votes2,
        'total': battle.total_votes,
        'pct1': battle.pct1,
        'pct2': battle.pct2,
    })


def battle_detail(request, battle_id):
    battle = get_object_or_404(Battle.objects.select_related('anime1', 'anime2', 'created_by'), id=battle_id)
    recent_votes = BattleVote.objects.filter(battle=battle).select_related('user').order_by('-created_at')[:20]
    user_vote = None
    if request.user.is_authenticated:
        uv = BattleVote.objects.filter(battle=battle, user=request.user).first()
        user_vote = uv.choice if uv else None
    return render(request, 'battle_detail.html', {
        'battle': battle,
        'recent_votes': recent_votes,
        'user_vote': user_vote,
    })


def tier_list_list(request):
    cached = cache.get('tier_list_list_data')
    if cached is not None:
        return render(request, 'tierlists.html', cached)

    tls_qs = TierList.objects.filter(is_public=True).select_related('user').prefetch_related('items__anime')
    paginator = Paginator(tls_qs, 24)
    page_number = request.GET.get('page', 1)
    tier_lists = paginator.get_page(page_number)
    context = {'tier_lists': tier_lists}
    cache.set('tier_list_list_data', context, 300)
    return render(request, 'tierlists.html', context)


@login_required
@transaction.atomic
def tier_list_create(request):
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        if title:
            import string, random, json
            slug = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
            tl = TierList.objects.create(user=request.user, title=title, slug=slug)
            UserActivity.objects.create(
                user=request.user,
                activity_type='TIER_LIST',
                description=title,
            )

            tier_data_raw = request.POST.get('tier_data', '')
            if tier_data_raw:
                try:
                    tier_data = json.loads(tier_data_raw)
                    order = 0
                    for tier, anime_ids in tier_data.items():
                        for aid in anime_ids:
                            try:
                                anime_obj = Anime.objects.filter(anilist_id=aid).first()
                                if not anime_obj:
                                    from apps.anime.services.anilist import anilist_client, AniListError
                                    try:
                                        d = anilist_client.get_anime_detail(int(aid))
                                        m = d.get('Media', {})
                                        if m:
                                            from apps.anime.services.sync import sync_anime_from_anilist
                                            anime_obj = sync_anime_from_anilist(m)
                                    except AniListError:
                                        pass
                                if anime_obj:
                                    TierListItem.objects.create(
                                        tier_list=tl, anime=anime_obj,
                                        tier=tier.upper(), order=order
                                    )
                                    order += 1
                            except Exception:
                                pass
                except json.JSONDecodeError:
                    pass
            return redirect('tier_list_view', slug=slug)
    return render(request, 'tierlist_create.html')


def tier_list_view(request, slug):
    tl = get_object_or_404(TierList, slug=slug, is_public=True)
    TierList.objects.filter(id=tl.id).update(view_count=F('view_count') + 1)
    tl.refresh_from_db()
    items = tl.items.select_related('anime').all()
    tiers = {'S': [], 'A': [], 'B': [], 'C': [], 'D': [], 'F': []}
    for item in items:
        tiers.setdefault(item.tier, []).append(item)
    tier_cfg = [
        ('S', 'S Tier', '#ef4444'),
        ('A', 'A Tier', '#f97316'),
        ('B', 'B Tier', '#eab308'),
        ('C', 'C Tier', '#22c55e'),
        ('D', 'D Tier', '#3b82f6'),
        ('F', 'F Tier', '#6b7280'),
    ]
    user_liked = False
    if request.user.is_authenticated:
        user_liked = TierListLike.objects.filter(tier_list=tl, user=request.user).exists()
    return render(request, 'tierlist_view.html', {
        'tier_list': tl, 'tiers': tiers, 'tier_cfg': tier_cfg, 'user_liked': user_liked,
    })


@login_required
@transaction.atomic
def tier_list_add_item(request, slug):
    tl = get_object_or_404(TierList, slug=slug, user=request.user)
    if request.method == 'POST':
        search_q = request.POST.get('search', '').strip()
        tier = request.POST.get('tier', 'B')
        if search_q:
            try:
                data = anilist_client.search(search=search_q, page=1, per_page=1)
                media = data.get('Page', {}).get('media', [])
                if media:
                    sync_anime_from_anilist(media[0])
                    anime = Anime.objects.filter(anilist_id=media[0]['id']).first()
                    if anime:
                        TierListItem.objects.create(tier_list=tl, anime=anime, tier=tier)
                        messages.success(request, f'Added {anime} to {tier} tier!')
                    else:
                        messages.error(request, 'Could not find that anime.')
            except AniListError:
                messages.error(request, 'Search failed.')
        return redirect('tier_list_view', slug=slug)
    return redirect('tier_list_view', slug=slug)


@login_required
@transaction.atomic
def tier_list_like_json(request, slug):
    from django.http import JsonResponse
    from django.db.models import F
    tl = get_object_or_404(TierList, slug=slug)
    like, created = TierListLike.objects.get_or_create(tier_list=tl, user=request.user)
    if created:
        TierList.objects.filter(id=tl.id).update(likes=F('likes') + 1)
        UserActivity.objects.create(
            user=request.user,
            activity_type='LIKE',
            description='Liked a tier list',
        )
        if tl.user != request.user:
            _create_notification(tl.user, f'{request.user.username} liked your tier list "{tl.title}"', url=f'/tierlists/{tl.slug}/', ntype='LIKE')
        tl_likes = TierList.objects.filter(id=tl.id).values_list('likes', flat=True).first() or 0
        return JsonResponse({'liked': True, 'likes': tl_likes})
    else:
        like.delete()
        TierList.objects.filter(id=tl.id).update(likes=F('likes') - 1)
        tl_likes = TierList.objects.filter(id=tl.id).values_list('likes', flat=True).first() or 0
        return JsonResponse({'liked': False, 'likes': tl_likes})


@login_required
@transaction.atomic
def tier_list_save_json(request, slug):
    from django.http import JsonResponse
    import json
    tl = get_object_or_404(TierList, slug=slug, user=request.user)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    valid_tiers = set(dict(TierList.TIERS).keys())
    tl.items.all().delete()
    order = 0
    for tier, anime_ids in data.items():
        tier = tier.upper()
        if tier not in valid_tiers:
            continue
        for aid in anime_ids:
            try:
                anime = Anime.objects.filter(anilist_id=int(aid)).first()
                if not anime:
                    from apps.anime.services.anilist import anilist_client
                    try:
                        d = anilist_client.get_anime_detail(int(aid))
                        m = d.get('Media', {})
                        if m:
                            from apps.anime.services.sync import sync_anime_from_anilist
                            anime = sync_anime_from_anilist(m)
                    except Exception:
                        pass
                if anime:
                    TierListItem.objects.create(
                        tier_list=tl, anime=anime, tier=tier, order=order
                    )
                    order += 1
            except Exception:
                pass

    tl.save(update_fields=['updated_at'])
    return JsonResponse({'ok': True, 'slug': tl.slug, 'count': order})


@login_required
def tier_list_prefill_api(request):
    from django.http import JsonResponse
    from apps.anime.models import Anime
    from apps.anime.services.anilist import anilist_client
    import json

    cache_key = 'tierlist_prefill'
    cached = cache.get(cache_key)
    if cached:
        return JsonResponse({'results': cached})

    pool = []
    seen = set()
    try:
        data = anilist_client.get_trending(page=1, per_page=15)
        for m in data.get('data', {}).get('Page', {}).get('media', []):
            aid = m['id']
            if aid not in seen:
                pool.append(m)
                seen.add(aid)
    except Exception:
        pass

    if len(pool) < 15:
        try:
            data = anilist_client.get_popular_this_season(False, page=1, per_page=15)
            for m in data.get('data', {}).get('Page', {}).get('media', []):
                aid = m['id']
                if aid not in seen:
                    pool.append(m)
                    seen.add(aid)
        except Exception:
            pass

    results = []
    for m in pool:
        anime = Anime.objects.filter(anilist_id=m['id']).first()
        if not anime:
            try:
                from apps.anime.services.sync import sync_anime_from_anilist
                anime = sync_anime_from_anilist(m)
            except Exception:
                pass
        if anime:
            results.append({
                'id': anime.anilist_id,
                'title': anime.display_title,
                'image': anime.cover_image_medium or (anime.cover_image_large or ''),
            })
        else:
            title = m.get('title', {}).get('romaji', m.get('title', {}).get('english', 'Unknown'))
            results.append({
                'id': m['id'],
                'title': title,
                'image': m.get('coverImage', {}).get('medium', ''),
            })

    cache.set(cache_key, results, 3600)
    return JsonResponse({'results': results})


def social_feed(request):
    from django.utils import timezone as tz
    from apps.feed.services import FeedBuilder
    from apps.anime.models import SocialPost, Battle
    from django.db.models import Count

    builder = FeedBuilder(request.user)
    feed_data = builder.build(page=1)

    now = tz.now()
    # Trending section data
    trending_discussions = SocialPost.objects.filter(
        reply_to__isnull=True,
        post_type__in=['discussion', 'trending', 'episode_discussion'],
        created_at__gte=now - timedelta(days=2),
    ).annotate(
        comment_count=Count('comments'),
        like_count=Count('liked_by'),
    ).order_by('-like_count', '-comment_count')[:5]

    most_active = SocialPost.objects.filter(
        reply_to__isnull=True,
        created_at__gte=now - timedelta(days=2),
    ).annotate(
        comment_count=Count('comments'),
        like_count=Count('liked_by'),
    ).order_by('-comment_count')[:5]

    top_battle = sorted(
        [b for b in Battle.objects.filter(created_at__gte=now - timedelta(days=7))],
        key=lambda b: b.votes1 + b.votes2, reverse=True
    )[:1]
    top_battle = top_battle[0] if top_battle else Battle.objects.filter(created_at__gte=now - timedelta(days=7)).order_by('-created_at').first()

    return render(request, 'social_feed.html', {
        'feed_items': feed_data['results'],
        'feed_meta': {
            'has_next': feed_data['has_next'],
            'next_page': feed_data['next_page'],
            'total': feed_data['total'],
        },
        'trending_discussions': trending_discussions,
        'most_active': most_active,
        'top_battle': top_battle,
    })


@login_required
def feed_api(request):
    from django.http import JsonResponse
    from apps.feed.services import FeedBuilder

    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('size', 20))
    builder = FeedBuilder(request.user)
    data = builder.build(page=page, page_size=page_size)
    return JsonResponse(data)


@login_required
@transaction.atomic
def social_create_post(request):
    if request.method == 'POST':
        body = request.POST.get('body', '').strip()
        title = request.POST.get('title', '').strip()
        anime_id = request.POST.get('anime_id', '').strip()
        if body:
            from apps.anime.models import Anime
            from apps.anime.services.sync import sync_anime_from_anilist
            from apps.anime.services.anilist import AniListClient
            anime = None
            if anime_id:
                try:
                    anime = Anime.objects.get(anilist_id=int(anime_id))
                except (Anime.DoesNotExist, ValueError):
                    try:
                        data = AniListClient().get_anime_detail(int(anime_id))
                        if data and data.get('Media'):
                            anime = sync_anime_from_anilist(data['Media'])
                    except Exception:
                        pass
            SocialPost.objects.create(user=request.user, body=body, title=title, anime=anime)
            from apps.feed.services import FeedBuilder
            FeedBuilder(request.user).invalidate()
            messages.success(request, 'Posted!' if not title else f'"{title}" posted!')
        return redirect('social_feed')
    return redirect('social_feed')


@login_required
@transaction.atomic
def social_like_post(request, post_id):
    post = get_object_or_404(SocialPost, id=post_id)
    like, created = SocialLike.objects.get_or_create(post=post, user=request.user)
    if not created:
        like.delete()
        SocialPost.objects.filter(id=post.id).update(likes=F('likes') - 1)
    else:
        SocialPost.objects.filter(id=post.id).update(likes=F('likes') + 1)
        if post.user != request.user:
            _create_notification(post.user, f'{request.user.username} liked your post',
                                 url='/social/', ntype='LIKE')
        UserActivity.objects.create(
            user=request.user,
            activity_type='LIKE',
            description='Liked a post',
        )
    return redirect('social_feed')


@login_required
@transaction.atomic
def social_like_json(request, post_id):
    from django.http import JsonResponse
    post = get_object_or_404(SocialPost, id=post_id)
    like, created = SocialLike.objects.get_or_create(post=post, user=request.user)
    if not created:
        like.delete()
        SocialPost.objects.filter(id=post.id).update(likes=F('likes') - 1)
    else:
        SocialPost.objects.filter(id=post.id).update(likes=F('likes') + 1)
        if post.user != request.user:
            _create_notification(post.user, f'{request.user.username} liked your post',
                                 url='/social/', ntype='LIKE')
        UserActivity.objects.create(
            user=request.user,
            activity_type='LIKE',
            description='Liked a post',
        )
    post.refresh_from_db()
    return JsonResponse({'likes': post.likes, 'liked': not created})


@login_required
@transaction.atomic
def poll_vote_json(request, post_id):
    from django.http import JsonResponse
    from apps.anime.models import SocialPost, Poll, PollOption, PollVote
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    post = get_object_or_404(SocialPost, id=post_id)
    try:
        poll = post.poll
    except Poll.DoesNotExist:
        return JsonResponse({'error': 'No poll on this post'}, status=404)
    option_id = request.POST.get('option_id')
    if not option_id:
        return JsonResponse({'error': 'Missing option_id'}, status=400)
    try:
        option = poll.options.get(id=int(option_id))
    except (PollOption.DoesNotExist, ValueError):
        return JsonResponse({'error': 'Invalid option'}, status=400)
    vote, created = PollVote.objects.get_or_create(option=option, user=request.user)
    if not created:
        vote.delete()
    options = [{'id': o.id, 'text': o.text, 'votes': o.vote_count, 'pct': o.percentage(poll.total_votes)} for o in poll.options.all()]
    return JsonResponse({'options': options, 'total': poll.total_votes, 'voted': not created, 'voted_option': option.id if not created else None})


@login_required
@transaction.atomic
def bookmark_toggle_json(request, post_id):
    from django.http import JsonResponse
    from apps.anime.models import SocialPost, Bookmark
    post = get_object_or_404(SocialPost, id=post_id)
    bm, created = Bookmark.objects.get_or_create(user=request.user, post=post)
    if not created:
        bm.delete()
    return JsonResponse({'bookmarked': created, 'count': post.bookmarks.count()})


def _share_post(user, post_type, title, body, content_object):
    from apps.anime.models import SocialPost
    from django.contrib.contenttypes.models import ContentType
    ct = ContentType.objects.get_for_model(content_object)
    post = SocialPost.objects.create(
        user=user, post_type=post_type, title=title, body=body,
        shared_ct=ct, shared_id=content_object.id,
    )
    UserActivity.objects.create(user=user, activity_type='SHARE', description=f'Shared a {post_type.replace("share_","")}')
    return post


@login_required
def share_battle(request, battle_id):
    from apps.anime.models import Battle
    battle = get_object_or_404(Battle, id=battle_id)
    title = f"⚔️ Battle: {battle.anime1.display_title} vs {battle.anime2.display_title}"
    body = f"Vote now: {battle.anime1.display_title} ({battle.pct1}%) vs {battle.anime2.display_title} ({battle.pct2}%) — {battle.total_votes} total votes"
    _share_post(request.user, 'share_battle', title[:200], body, battle)
    from apps.feed.services import FeedBuilder
    FeedBuilder(request.user).invalidate()
    messages.success(request, 'Battle shared to feed!')
    return redirect('social_feed')


@login_required
def share_tierlist(request, slug):
    from apps.anime.models import TierList
    tl = get_object_or_404(TierList, slug=slug)
    title = f"📊 Tier List: {tl.name}"
    body = f"Check out my tier list: {tl.name} by {request.user.username}"
    _share_post(request.user, 'share_tierlist', title[:200], body, tl)
    from apps.feed.services import FeedBuilder
    FeedBuilder(request.user).invalidate()
    messages.success(request, 'Tier list shared to feed!')
    return redirect('social_feed')


@login_required
def social_comment(request, post_id):
    if request.method == 'POST':
        body = request.POST.get('body', '').strip()
        if body:
            from apps.anime.models import Comment
            from django.contrib.contenttypes.models import ContentType
            post = get_object_or_404(SocialPost, id=post_id)
            ct = ContentType.objects.get_for_model(SocialPost)
            comment = Comment.objects.create(
                user=request.user,
                body=body,
                content_type=ct,
                object_id=post.id,
            )
            if request.headers.get('Accept') == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                from django.http import JsonResponse
                return JsonResponse({
                    'id': comment.id,
                    'user': comment.user.username,
                    'user_id': comment.user.id,
                    'avatar': comment.user.avatar.url if comment.user.avatar else '',
                    'body': comment.body,
                    'is_spoiler': comment.is_spoiler,
                    'created_at': comment.created_at.isoformat(),
                })
            if post.user != request.user:
                _create_notification(post.user, f'{request.user.username} commented on your post', url='/social/', ntype='COMMENT')
    return redirect('social_feed')


@login_required
def social_delete_post(request, post_id):
    post = get_object_or_404(SocialPost, id=post_id, user=request.user)
    post.delete()
    return redirect('social_feed')


@login_required
def social_post_comments(request, post_id):
    from django.http import JsonResponse
    from django.contrib.contenttypes.models import ContentType
    post = get_object_or_404(SocialPost, id=post_id)
    ct = ContentType.objects.get_for_model(SocialPost)
    comments = Comment.objects.filter(
        content_type=ct, object_id=post.id, parent__isnull=True
    ).select_related('user').order_by('created_at')[:20]
    data = [{
        'id': c.id,
        'user': c.user.username,
        'user_id': c.user.id,
        'avatar': c.user.avatar.url if c.user.avatar else '',
        'body': c.body,
        'is_spoiler': c.is_spoiler,
        'created_at': c.created_at.isoformat(),
    } for c in comments]
    return JsonResponse({'comments': data})


@login_required
@transaction.atomic
def social_follow(request, username):
    User = get_user_model()
    target = get_object_or_404(User, username=username)
    if target != request.user:
        follow, created = UserFollow.objects.get_or_create(follower=request.user, following=target)
        if not created:
            follow.delete()
        else:
            _create_notification(target, f'{request.user.username} started following you',
                                 url='/social/', ntype='FOLLOW')
    return redirect('social_feed')


@login_required
def anime_wrapped(request):
    entries = WatchlistEntry.objects.filter(user=request.user).select_related('anime').prefetch_related('anime__genres')
    total_completed = entries.filter(status='COMPLETED').count()
    total_watching = entries.filter(status='WATCHING').count()
    total_episodes = sum(e.anime.episodes or 0 for e in entries.filter(status='COMPLETED'))
    minutes_watched = sum((e.anime.episodes or 0) * (e.anime.duration or 24) for e in entries.filter(status='COMPLETED'))
    hours_watched = minutes_watched // 60
    genre_counts = {}
    for e in entries:
        for g in e.anime.genres.all():
            genre_counts[g.name] = genre_counts.get(g.name, 0) + 1
    top_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    score_entries = [e for e in entries if e.score and e.score > 0]
    avg_score = round(sum(e.score for e in score_entries) / len(score_entries), 1) if score_entries else 0
    top_rated = sorted(score_entries, key=lambda x: x.score, reverse=True)[:5] if score_entries else []
    return render(request, 'wrapped.html', {
        'total_completed': total_completed,
        'total_watching': total_watching,
        'total_episodes': total_episodes,
        'hours_watched': hours_watched,
        'top_genres': top_genres,
        'avg_score': avg_score,
        'top_rated': top_rated,
    })


def personality_quiz(request):
    questions_data = [
        {
            "q": "Your friends describe you as:",
            "options": [
                {"text": "Brave and impulsive", "char": "Naruto", "image": "https://s4.anilist.co/file/anilistcdn/character/large/b17.jpg"},
                {"text": "Calm and strategic", "char": "Lelouch", "image": "https://s4.anilist.co/file/anilistcdn/character/large/b15771.jpg"},
                {"text": "Loyal and strong", "char": "Levi", "image": "https://s4.anilist.co/file/anilistcdn/character/large/b3511.jpg"},
                {"text": "Mysterious and cool", "char": "Gojo", "image": "https://s4.anilist.co/file/anilistcdn/character/large/b118481.jpg"},
            ]
        },
        {
            "q": "Choose your ideal power:",
            "options": [
                {"text": "Never give up", "char": "Naruto", "image": ""},
                {"text": "Absolute control", "char": "Lelouch", "image": ""},
                {"text": "Perfect execution", "char": "Levi", "image": ""},
                {"text": "Limitless potential", "char": "Gojo", "image": ""},
            ]
        },
        {
            "q": "Your ideal Saturday:",
            "options": [
                {"text": "Training with friends", "char": "Naruto", "image": ""},
                {"text": "Playing chess alone", "char": "Lelouch", "image": ""},
                {"text": "Cleaning then napping", "char": "Levi", "image": ""},
                {"text": "Doing whatever I want", "char": "Gojo", "image": ""},
            ]
        },
        {
            "q": "How do you handle problems?",
            "options": [
                {"text": "Charge in headfirst", "char": "Naruto", "image": ""},
                {"text": "Outsmart everyone", "char": "Lelouch", "image": ""},
                {"text": "Analyze then strike", "char": "Levi", "image": ""},
                {"text": "Stay chill, it's fine", "char": "Gojo", "image": ""},
            ]
        },
        {
            "q": "Pick a color:",
            "options": [
                {"text": "Orange", "char": "Naruto", "image": ""},
                {"text": "Purple", "char": "Lelouch", "image": ""},
                {"text": "Teal", "char": "Levi", "image": ""},
                {"text": "White", "char": "Gojo", "image": ""},
            ]
        },
    ]
    results = {
        "Naruto": {"title": "Naruto Uzumaki", "anime": "Naruto", "desc": "You never give up! You're determined, loud, and loyal to your friends. You believe hard work beats talent.", "image": "https://s4.anilist.co/file/anilistcdn/character/large/b17.jpg", "color": "#f97316"},
        "Lelouch": {"title": "Lelouch vi Britannia", "anime": "Code Geass", "desc": "You're a master strategist. You think 10 steps ahead and will do whatever it takes to achieve your goals.", "image": "https://s4.anilist.co/file/anilistcdn/character/large/b15771.jpg", "color": "#8b5cf6"},
        "Levi": {"title": "Levi Ackerman", "anime": "Attack on Titan", "desc": "You're clean, efficient, and deadly serious when it counts. You have high standards and zero tolerance for nonsense.", "image": "https://s4.anilist.co/file/anilistcdn/character/large/b3511.jpg", "color": "#06b6d4"},
        "Gojo": {"title": "Satoru Gojo", "anime": "Jujutsu Kaisen", "desc": "You're the strongest — and you know it. Confident, playful, but unstoppable when things get real.", "image": "https://s4.anilist.co/file/anilistcdn/character/large/b118481.jpg", "color": "#e2e8f0"},
    }
    result_char = None
    if request.method == 'POST':
        answers = []
        for i in range(5):
            ans = request.POST.get(f'q{i}')
            if ans:
                answers.append(ans)
        if answers:
            from collections import Counter
            counts = Counter(answers)
            result_char = counts.most_common(1)[0][0]
    return render(request, 'personality_quiz.html', {
        'questions': questions_data,
        'results': results,
        'result_char': result_char,
    })


@login_required
def watch_time(request):
    entries = WatchlistEntry.objects.filter(
        user=request.user,
        status__in=['COMPLETED', 'WATCHING'],
    ).select_related('anime').prefetch_related('anime__genres')

    total_hours = 0
    breakdown = []
    for entry in entries:
        if entry.anime.episodes and entry.anime.duration:
            ep_count = entry.episodes_watched if entry.status == 'WATCHING' else entry.anime.episodes
            mins = ep_count * entry.anime.duration
            hours = mins / 60
            total_hours += hours
            breakdown.append({
                'anime': entry.anime,
                'episodes': ep_count,
                'duration': entry.anime.duration,
                'hours': round(hours, 1),
            })

    breakdown.sort(key=lambda x: x['hours'], reverse=True)

    genres = {}
    for item in breakdown[:50]:
        anime = item['anime']
        for g in anime.genres.all():
            genres[g.name] = genres.get(g.name, 0) + item['hours']

    return render(request, 'watch_time.html', {
        'total_hours': round(total_hours, 1),
        'breakdown': breakdown[:30],
        'genres': sorted(genres.items(), key=lambda x: x[1], reverse=True)[:10],
        'total_anime': len(breakdown),
    })


@login_required
def recommendations_page(request):
    from apps.anime.services.anilist import anilist_client
    import json

    recs = list(get_recommendations_for_user(request.user, limit=20))
    with_reasons = []

    user_genres = {}
    watched_entries = WatchlistEntry.objects.filter(
        user=request.user,
        status__in=['COMPLETED', 'WATCHING'],
    ).select_related('anime').prefetch_related('anime__genres')

    for entry in watched_entries:
        for g in entry.anime.genres.all():
            user_genres[g.name] = user_genres.get(g.name, 0) + 1

    top_user_genres = sorted(user_genres.items(), key=lambda x: x[1], reverse=True)[:5]

    for anime in recs:
        matching_genres = [g.name for g in anime.genres.all() if g.name in user_genres]
        reason = f"Because you like {', '.join(matching_genres[:2])}" if matching_genres else "Trending now"
        with_reasons.append({
            'anime': anime,
            'reason': reason,
        })

    return render(request, 'recommendations.html', {
        'recommendations': with_reasons,
        'top_genres': top_user_genres,
    })


def _fetch_anime(search_term, per_page=1):
    """Helper: search AniList and return first result's media dict or None."""
    try:
        data = anilist_client.search(search=search_term, page=1, per_page=per_page)
        results = data.get('Page', {}).get('media', [])
        return results[0] if results else None
    except AniListError:
        return None

def _anime_to_card(a, detail=False):
    """Convert AniList media dict to a card dict."""
    title = a.get('title', {}).get('english') or a.get('title', {}).get('romaji', 'Unknown')
    card = {
        'id': a['id'], 'title': title,
        'image': a.get('coverImage', {}).get('medium', ''),
        'score': a.get('averageScore'),
        'format': a.get('format', ''),
        'episodes': a.get('episodes'),
    }
    if detail:
        card['genres'] = a.get('genres', [])[:3]
    return card

def _clean_desc(desc, length=350):
    import re
    return re.sub(r'<[^>]+>', '', desc)[:length] if desc else 'No description available.'

def _format_info(a, title=None):
    """Build a detailed info string for an anime."""
    t = title or (a.get('title', {}).get('english') or a.get('title', {}).get('romaji', 'Unknown'))
    score = a.get('averageScore', '?')
    eps = a.get('episodes', '?')
    status = a.get('status', '').replace('_', ' ').title()
    genres = ', '.join(a.get('genres', [])[:4]) or 'N/A'
    season = a.get('season', '')
    year = a.get('seasonYear', '')
    season_str = f' {season.title()} {year}' if season and year else ''
    studio_nodes = (a.get('studios') or {}).get('nodes', [])
    studio = studio_nodes[0]['name'] if studio_nodes else 'Unknown'
    fmt = a.get('format', '').replace('_', ' ').title()
    duration = a.get('duration', '?')
    pop = a.get('popularity', '?')
    favs = a.get('favourites', '?')
    desc = _clean_desc(a.get('description', ''), 300)
    return (
        f"📺 **{t}**{season_str}\n\n"
        f"⭐ **{score}/10**  |  📦 {eps} eps  |  🎬 {fmt}  |  ⏱ {duration}m\n"
        f"🏢 {studio}  |  📊 {status}  |  👑 {pop}  |  ❤️ {favs}\n"
        f"🏷️ {genres}\n\n"
        f"{desc}...\n\n"
        f"👉 Click the card to see full details!"
    ), t


@ratelimit(key='ip', rate='20/m', method='GET', block=False)
def chat_ai(request):
    from django.http import JsonResponse, HttpResponse
    import random, re

    if getattr(request, 'limited', False):
        return JsonResponse({'reply': '⏳ Whoa there! You\'re asking too fast. Slow down a bit and try again in a moment.', 'anime': []}, status=429)

    msg = request.GET.get('msg', '').strip()
    if not msg:
        return JsonResponse({'reply': 'Hey! Ask me about any anime — "tell me about AoT", "recommend something funny", "compare Naruto vs One Piece", "what\'s trending?" 🎬', 'anime': []})

    msg_lower = msg.lower().strip()

    # ─── Greetings / chitchat ───────────────────────────────────
    if any(g == msg_lower or msg_lower.startswith(g) for g in ['hi','hello','hey','sup','yo','whats up','good morning','good evening','howdy']):
        replies = [
            'Hey! 🖐️ Ask me anything about anime!',
            'Yo! What anime are we talking about today?',
            'Hey there! I know a ton about anime — try me!',
            'Sup! Wanna compare two shows or get a recommendation?',
        ]
        return JsonResponse({'reply': random.choice(replies), 'anime': []})

    if any(t in msg_lower for t in ['thanks','thank you','thx','appreciate it','ty']):
        return JsonResponse({'reply': 'Anytime! 🫡 Hit me up whenever you need anime wisdom.', 'anime': []})

    if any(w in msg_lower for w in ['bye','goodbye','see you','cya','later']):
        return JsonResponse({'reply': 'Later! 🖐️ Come back when you need more anime recs!', 'anime': []})

    # ─── How many episodes? ─────────────────────────────────────
    ep_match = re.search(r'(?:how many episodes|episodes does|episode count|total episodes|number of episodes)(?:\s+does|\s+in|\s+of)?\s+(.+?)(?:\?|$)', msg_lower)
    if ep_match:
        a = _fetch_anime(ep_match.group(1).strip())
        if a:
            eps = a.get('episodes', '?')
            title = a.get('title', {}).get('english') or a.get('title', {}).get('romaji', 'Unknown')
            status = a.get('status', '').replace('_', ' ').title()
            reply = f"📦 **{title}** has **{eps}** episodes and is currently **{status}**."
            return JsonResponse({'reply': reply, 'anime': [_anime_to_card(a)]})

    # ─── What studio / who made? ────────────────────────────────
    studio_match = re.search(r'(?:what studio|who (?:made|created|animated|produced)|studio that|which studio|made by|animated by|created by)\s+(.+?)(?:\?|$)', msg_lower)
    if studio_match:
        a = _fetch_anime(studio_match.group(1).strip())
        if a:
            title = a.get('title', {}).get('english') or a.get('title', {}).get('romaji', 'Unknown')
            nodes = (a.get('studios') or {}).get('nodes', [])
            if nodes:
                studios = ', '.join(s['name'] for s in nodes[:3])
                reply = f"🏢 **{title}** was animated by **{studios}**."
            else:
                reply = f"Hmm, I couldn't find the studio info for **{title}**."
            return JsonResponse({'reply': reply, 'anime': [_anime_to_card(a)]})

    # ─── When did X come out? ───────────────────────────────────
    date_match = re.search(r'(?:when (?:does|did|is)|release date|what year|what season|air date|released)\s+(.+?)(?:\?|$)', msg_lower)
    if date_match:
        a = _fetch_anime(date_match.group(1).strip())
        if a:
            title = a.get('title', {}).get('english') or a.get('title', {}).get('romaji', 'Unknown')
            season = a.get('season', '')
            year = a.get('seasonYear', '')
            status = a.get('status', '').replace('_', ' ').title()
            if season and year:
                reply = f"📅 **{title}** aired in **{season.title()} {year}** and is currently **{status}**."
            elif year:
                reply = f"📅 **{title}** came out in **{year}** and is currently **{status}**."
            else:
                reply = f"📅 **{title}** is currently **{status}**."
            return JsonResponse({'reply': reply, 'anime': [_anime_to_card(a)]})

    # ─── Is X finished / still airing? ──────────────────────────
    status_match = re.search(r'(?:is\s+|is\s+.+?\s+)?(finished|still airing|ongoing|complete|cancelled|on hiatus|hiatus|done|over)\s*(?:\?|$)', msg_lower)
    if status_match:
        # Try to extract anime name from surrounding text
        a = _fetch_anime(msg_lower.replace(status_match.group(1), '').strip())
        if a:
            title = a.get('title', {}).get('english') or a.get('title', {}).get('romaji', 'Unknown')
            status = a.get('status', '').replace('_', ' ').title()
            eps = a.get('episodes', '?')
            reply = f"📊 **{title}** is **{status}** with **{eps}** episodes total."
            return JsonResponse({'reply': reply, 'anime': [_anime_to_card(a)]})

    # ─── What genre is X? ──────────────────────────────────────
    genre_match = re.search(r'(?:what genre|genre of|genres of|what type of)\s+(.+?)(?:\?|$)', msg_lower)
    if genre_match:
        a = _fetch_anime(genre_match.group(1).strip())
        if a:
            title = a.get('title', {}).get('english') or a.get('title', {}).get('romaji', 'Unknown')
            genres = a.get('genres', [])
            if genres:
                reply = f"🏷️ **{title}** genres: **{', '.join(genres[:6])}**."
            else:
                reply = f"No genre info available for **{title}**."
            return JsonResponse({'reply': reply, 'anime': [_anime_to_card(a)]})

    # ─── What's the score / rating of X? ────────────────────────
    score_match = re.search(r"(?:what(?:'s| is|)\s*(?:the\s*)?(?:score|rating)|score of|rating of|how (?:is|'s)\s+.+?\s+rated|how good is)\s+(.+?)(?:\?|$)", msg_lower)
    if score_match:
        search_term = score_match.group(1).strip()
        # Clean up false matches
        for w in ['anime', 'show', 'series', 'this']:
            if search_term == w:
                search_term = ''
                break
        if search_term:
            a = _fetch_anime(search_term)
            if a:
                title = a.get('title', {}).get('english') or a.get('title', {}).get('romaji', 'Unknown')
                score = a.get('averageScore', '?')
                pop = a.get('popularity', '?')
                reply = f"⭐ **{title}** has a score of **{score}/10** with **{pop}** people watching it!"
                return JsonResponse({'reply': reply, 'anime': [_anime_to_card(a)]})

    # ─── How long is X? (duration) ──────────────────────────────
    dur_match = re.search(r'(?:how long|duration|length|how many minutes|run time)\s+(?:is|does|of)?\s*(.+?)(?:\?|$)', msg_lower)
    if dur_match:
        a = _fetch_anime(dur_match.group(1).strip())
        if a:
            title = a.get('title', {}).get('english') or a.get('title', {}).get('romaji', 'Unknown')
            dur = a.get('duration', '?')
            eps = a.get('episodes', '?')
            total = (dur * eps) // 60 if dur and eps and dur != '?' and eps != '?' else '?'
            reply = f"⏱ **{title}** — **{dur} min** per episode, **{eps} eps** total (~{total}h)." if total != '?' else f"⏱ **{title}** — **{dur} min** per episode."
            return JsonResponse({'reply': reply, 'anime': [_anime_to_card(a)]})

    # ─── Similar / like X ──────────────────────────────────────
    like_match = re.search(r'(?:similar to|like|reminiscent of|reminds me of|something like|anything like|shows like|anime like)\s+(.+?)(?:\?|$)', msg_lower)
    if like_match:
        source_a = _fetch_anime(like_match.group(1).strip())
        if source_a:
            src_genres = source_a.get('genres', [])
            try:
                data = anilist_client.search(genres=src_genres[:2] if src_genres else None, sort=['TRENDING_DESC'], page=1, per_page=6)
                results = data.get('Page', {}).get('media', [])
                filtered = [a for a in results if a['id'] != source_a['id']][:6]
                if filtered:
                    src_title = source_a.get('title', {}).get('english') or source_a.get('title', {}).get('romaji', 'Unknown')
                    anime_list = [_anime_to_card(a) for a in filtered]
                    return JsonResponse({'reply': f'🔍 If you like **{src_title}**, you might enjoy these:', 'anime': anime_list})
            except AniListError:
                pass

    # ─── Tell me about X / what is X ────────────────────────────
    about_match = re.search(r'(?:tell me about|what is|what\'s|whats|about|info on|details on|describe|give me info)\s+(.+?)(?:\?|$)', msg_lower)
    if about_match:
        a = _fetch_anime(about_match.group(1).strip())
        if a:
            reply, title = _format_info(a)
            return JsonResponse({'reply': reply, 'anime': [_anime_to_card(a)]})

    # ─── Compare / which is better ──────────────────────────────
    compare_patterns = [
        r'compare\s+(.+?)\s+(?:vs|versus|and|with|or)\s+(.+)',
        r'which is better\s+(.+?)\s+(?:vs|versus|or|and)\s+(.+)',
        r'which (?:one|show|anime) (?:is better|should i watch)\s+(.+?)\s+(?:or|vs)\s+(.+)',
        r'(.+?)\s+(?:vs|versus)\s+(.+)',
    ]
    compare_match = None
    for pat in compare_patterns:
        compare_match = re.search(pat, msg_lower)
        if compare_match:
            break
    if compare_match:
        name1, name2 = compare_match.group(1).strip(), compare_match.group(2).strip()
        # Ignore if names are too generic
        if len(name1) > 2 and len(name2) > 2 and name1 not in ('me', 'anime', 'show') and name2 not in ('me', 'anime', 'show'):
            r1, r2 = _fetch_anime(name1, 6), _fetch_anime(name2, 6)
            if r1 and r2:
                t1 = r1.get('title', {}).get('english') or r1.get('title', {}).get('romaji', '?')
                t2 = r2.get('title', {}).get('english') or r2.get('title', {}).get('romaji', '?')
                s1, s2 = r1.get('averageScore'), r2.get('averageScore')
                e1, e2 = r1.get('episodes', '?'), r2.get('episodes', '?')
                p1, p2 = r1.get('popularity', '?'), r2.get('popularity', '?')
                f1, f2 = r1.get('favourites', '?'), r2.get('favourites', '?')
                g1 = ', '.join(r1.get('genres', [])[:3]) or 'N/A'
                g2 = ', '.join(r2.get('genres', [])[:3]) or 'N/A'
                fmt1 = r1.get('format', '').replace('_', ' ').title()
                fmt2 = r2.get('format', '').replace('_', ' ').title()
                yr1 = r1.get('seasonYear', '?')
                yr2 = r2.get('seasonYear', '?')

                # Determine winner in different categories
                score_winner = t1 if (isinstance(s1,(int,float)) and isinstance(s2,(int,float)) and s1 > s2) else (t2 if isinstance(s1,(int,float)) and isinstance(s2,(int,float)) and s2 > s1 else 'Tie')
                pop_winner = t1 if p1 > p2 else (t2 if p2 > p1 else 'Tie')
                fav_winner = t1 if f1 > f2 else (t2 if f2 > f1 else 'Tie')

                s1_str = f'{s1}/10' if isinstance(s1,(int,float)) else '?'
                s2_str = f'{s2}/10' if isinstance(s2,(int,float)) else '?'

                reply = (
                    f"⚔️ **{t1}** vs **{t2}**\n\n"
                    f"————— {t1} —————\n"
                    f"⭐ Score: {s1_str}  |  📦 {e1} eps  |  🎬 {fmt1}  |  {yr1}\n"
                    f"🏷️ {g1}  |  👑 {p1}  |  ❤️ {f1}\n\n"
                    f"————— {t2} —————\n"
                    f"⭐ Score: {s2_str}  |  📦 {e2} eps  |  🎬 {fmt2}  |  {yr2}\n"
                    f"🏷️ {g2}  |  👑 {p2}  |  ❤️ {f2}\n\n"
                    f"🏆 **Score:** {score_winner} wins!\n"
                    f"📊 **Popularity:** {pop_winner}\n"
                    f"❤️ **Favorites:** {fav_winner}"
                )
                anime_list = [_anime_to_card(r1), _anime_to_card(r2)]
                return JsonResponse({'reply': reply, 'anime': anime_list})

    # ─── Trending / popular / top ────────────────────────────────
    if any(w in msg_lower for w in ['trending', 'trending now', 'whats hot', 'whats popular']):
        try:
            data = anilist_client.get_trending(page=1, per_page=6)
            results = data.get('Page', {}).get('media', [])
            anime_list = [_anime_to_card(a) for a in results]
            return JsonResponse({'reply': '🔥 **Trending Now** — These are what everyone\'s watching:', 'anime': anime_list})
        except AniListError:
            pass

    if any(w in msg_lower for w in ['top rated', 'top anime', 'best anime', 'best ever', 'greatest of all time', 'highest rated']):
        try:
            data = anilist_client.get_top_rated(page=1, per_page=6)
            results = data.get('Page', {}).get('media', [])
            anime_list = [_anime_to_card(a) for a in results]
            return JsonResponse({'reply': '🏆 **Top Rated of All Time** — The cream of the crop:', 'anime': anime_list})
        except AniListError:
            pass

    # ─── Currently airing / this season ─────────────────────────
    if any(w in msg_lower for w in ['currently airing', 'this season', 'airing now', 'new this season', 'whats airing']):
        try:
            from datetime import datetime as dt2
            now = dt2.now()
            month = now.month
            season_map = {3:'SPRING',4:'SPRING',5:'SPRING',6:'SUMMER',7:'SUMMER',8:'SUMMER',9:'FALL',10:'FALL',11:'FALL'}
            ssn = season_map.get(month, 'WINTER')
            data = anilist_client.get_popular_this_season(season=ssn, year=now.year, page=1, per_page=6)
            results = data.get('Page', {}).get('media', [])
            anime_list = [_anime_to_card(a) for a in results]
            return JsonResponse({'reply': f'📺 **Popular This {ssn.title()}** — What everyone\'s watching right now:', 'anime': anime_list})
        except AniListError:
            pass

    # ─── What should I watch? — Personalized ────────────────────
    if request.user.is_authenticated and any(p in msg_lower for p in ['what should i watch', 'recommend me something', 'suggest me something', 'what do you recommend', 'i dont know what to watch', 'anything good', 'give me a recommendation']):
        try:
            recs = list(get_recommendations_for_user(request.user, limit=6))
            if recs:
                anime_list = [{'id': a.anilist_id, 'title': a.display_title, 'image': a.cover_image_medium or a.cover_image_large, 'score': a.average_score, 'format': a.format, 'episodes': a.episodes} for a in recs]
                return JsonResponse({'reply': '🎯 **Based on your watch history**, you might love these:', 'anime': anime_list})
        except Exception:
            pass
        # Fallback for unauthenticated or failed recs
        try:
            data = anilist_client.get_trending(page=1, per_page=6)
            results = data.get('Page', {}).get('media', [])
            anime_list = [_anime_to_card(a) for a in results]
            return JsonResponse({'reply': '🎯 Here are some trending picks to get you started:', 'anime': anime_list})
        except AniListError:
            pass

    # ─── Random pick ────────────────────────────────────────────
    if any(p in msg_lower for p in ['random', 'surprise me', 'surprise', 'give me something', 'anything', 'pick something']):
        try:
            page = random.randint(1, 15)
            data = anilist_client.search(page=page, per_page=10)
            results = data.get('Page', {}).get('media', [])
            if results:
                chosen = random.choice(results)
                title = chosen.get('title', {}).get('english') or chosen.get('title', {}).get('romaji', 'Unknown')
                anime_list = [_anime_to_card(chosen)]
                return JsonResponse({'reply': f'🎲 **Random Pick:** {title} — give it a shot!', 'anime': anime_list})
        except AniListError:
            pass

    # ─── Genre / mood detection ─────────────────────────────────
    genre_map = {
        'action': 'Action', 'romance': 'Romance', 'romantic': 'Romance', 'love': 'Romance',
        'comedy': 'Comedy', 'funny': 'Comedy', 'horror': 'Horror', 'scary': 'Horror',
        'fantasy': 'Fantasy', 'sci-fi': 'Sci-Fi', 'scifi': 'Sci-Fi', 'isekai': 'Isekai',
        'drama': 'Drama', 'thriller': 'Thriller', 'mystery': 'Mystery',
        'slice of life': 'Slice of Life', 'slice-of-life': 'Slice of Life',
        'sports': 'Sports', 'music': 'Music', 'mecha': 'Mecha',
        'psychological': 'Psychological', 'supernatural': 'Supernatural',
        'adventure': 'Adventure', 'ecchi': 'Ecchi',
        'sad': 'Drama', 'dark': 'Horror', 'happy': 'Comedy',
        'chill': 'Slice of Life', 'hype': 'Action', 'mind games': 'Psychological',
        'emotional': 'Drama', 'action packed': 'Action',
    }
    mood_reply = {
        'action': '⚡ **Action mode!** Here are some hype bangers:', 'romance': '❤️ **Love is in the air.** Check these romance anime:',
        'comedy': '😂 **Need a laugh?** These will have you rolling:', 'horror': '💀 **Dark and twisted.** You asked for it:',
        'fantasy': '🧙‍♂️ **Escape reality** with these fantasy worlds:', 'sci-fi': '🚀 **Sci-fi greatness** incoming:',
        'slice of life': '🌙 **Chill vibes only.** Relax and unwind:', 'psychological': '🧠 **Mind = blown.** These will mess with your head:',
        'thriller': '😬 **Edge of your seat** thriller picks:', 'sports': '🏀 **Get hyped** with these sports anime:',
        'music': '🎵 **Feel the rhythm** with these music anime:', 'adventure': '🗺️ **Ready for a journey?** Check these out:',
        'isekai': '🌍 **Trapped in another world!** Classic isekai bangers:', 'mystery': '🔍 **Mystery time.** Can you solve it?',
        'drama': '🎭 **Emotional damage incoming.** These drama hits:', 'supernatural': '👻 **Supernatural vibes.** Something spooky:',
        'ecchi': '😏 **You asked for it.** Ecchi picks:',
    }

    detected_genres = []
    sort = ['TRENDING_DESC']
    search_q = None

    for word, genre in genre_map.items():
        if word in msg_lower:
            detected_genres.append(genre)
            break

    if any(w in msg_lower for w in ['top', 'best', 'greatest', 'highest rated']):
        sort = ['SCORE_DESC']
    if any(w in msg_lower for w in ['popular', 'trending']):
        sort = ['TRENDING_DESC']
    if any(w in msg_lower for w in ['new', 'recent', 'upcoming', 'latest']):
        sort = ['START_DATE_DESC']

    for prefix in ['recommend', 'suggest', 'show me', 'find', 'search', 'i want', 'looking for', 'give me', 'need']:
        if prefix in msg_lower:
            after = msg_lower.split(prefix, 1)[-1].strip()
            after = after.replace('anime', '').replace('some', '').replace('a ', '').replace('me', '').replace('please', '').replace('now', '').replace('i want', '').replace('to watch', '').strip()
            if after and after not in ('', 'anime'):
                search_q = after

    try:
        data = anilist_client.search(
            search=search_q if search_q and not detected_genres else (search_q or None),
            genres=detected_genres if detected_genres else None,
            sort=sort,
            page=1, per_page=6,
        )
        results = data.get('Page', {}).get('media', [])

        anime_list = [_anime_to_card(a) for a in results]

        if anime_list:
            genre_key = detected_genres[0].lower().replace(' ', '-') if detected_genres else None
            reply = mood_reply.get(genre_key, f"Here's what I found{' for **' + search_q + '**' if search_q else ''}:")
            return JsonResponse({'reply': reply, 'anime': anime_list})
        else:
            # Ultimate fallback — try searching directly with the raw message
            try:
                data2 = anilist_client.search(search=msg_lower, page=1, per_page=6)
                results2 = data2.get('Page', {}).get('media', [])
                if results2:
                    anime_list2 = [_anime_to_card(a) for a in results2]
                    return JsonResponse({'reply': f'Not sure what you meant, but here are some results for **"{msg}"**:', 'anime': anime_list2})
            except AniListError:
                pass

            return JsonResponse({'reply': "I couldn't find anything for that. Try:\n• **tell me about AoT**\n• **compare Naruto vs One Piece**\n• **recommend something funny**\n• **what's trending?**\n• **how many episodes does Death Note have**", 'anime': []})

    except AniListError as e:
        logger.error(f"Chat AI search failed: {e}")
        return JsonResponse({'reply': 'Oops, the anime database is acting up. Try again in a bit!', 'anime': []})
    except Exception as e:
        logger.error(f"Chat AI error: {e}")
        return JsonResponse({'reply': 'Something went wrong. Try asking differently!', 'anime': []})


def _create_notification(user, title, message='', url='', ntype='SYSTEM'):
    from apps.anime.models import Notification
    Notification.objects.create(user=user, title=title, message=message, url=url, notification_type=ntype)


def _check_achievements(user):
    from apps.watchlist.models import Achievement
    from apps.watchlist.models import CustomList
    from apps.anime.models import Review

    total = WatchlistEntry.objects.filter(user=user).count()
    completed = WatchlistEntry.objects.filter(user=user, status='COMPLETED').count()
    watching = WatchlistEntry.objects.filter(user=user, status='WATCHING').count()
    reviews = Review.objects.filter(user=user).count()
    lists = CustomList.objects.filter(user=user).count()

    total_hours = 0
    for entry in WatchlistEntry.objects.filter(user=user, status__in=['COMPLETED', 'WATCHING']).select_related('anime'):
        if entry.anime.episodes and entry.anime.duration:
            ep = entry.episodes_watched if entry.status == 'WATCHING' else entry.anime.episodes
            total_hours += (ep * entry.anime.duration) / 60

    checks = {
        'first_anime': total >= 1,
        'watching_5': watching >= 5,
        'completed_10': completed >= 10,
        'completed_50': completed >= 50,
        'completed_100': completed >= 100,
        'watchlist_25': total >= 25,
        'watchlist_100': total >= 100,
        'review_first': reviews >= 1,
        'review_10': reviews >= 10,
        'list_creator': lists >= 1,
        'hours_100': total_hours >= 100,
        'hours_500': total_hours >= 500,
    }

    new_unlocks = []
    for key, condition in checks.items():
        if condition and not Achievement.objects.filter(user=user, key=key).exists():
            defs = ACHIEVEMENT_DEFS.get(key, {})
            Achievement.objects.create(
                user=user,
                key=key,
                title=defs.get('title', key),
                description=defs.get('description', ''),
                icon=defs.get('icon', '🏆'),
            )
            new_unlocks.append(defs.get('title', key))

    if new_unlocks:
        for name in new_unlocks:
            pass


@login_required
def anime_discussions(request, anime_id):
    from apps.anime.models import Anime, DiscussionThread
    from apps.anime.forms import DiscussionThreadForm

    anime = get_object_or_404(Anime, anilist_id=anime_id)

    if request.method == 'POST':
        form = DiscussionThreadForm(request.POST)
        if form.is_valid():
            thread = form.save(commit=False)
            thread.anime = anime
            thread.user = request.user
            thread.save()
            return redirect('discussion_thread', thread_id=thread.id)
    else:
        form = DiscussionThreadForm()

    threads_qs = DiscussionThread.objects.filter(anime=anime).select_related('user').prefetch_related('comments')
    episodes_filter = request.GET.get('episode', '')
    if episodes_filter and episodes_filter.isdigit():
        threads_qs = threads_qs.filter(episode_number=int(episodes_filter))
    paginator = Paginator(threads_qs, 15)
    page_number = request.GET.get('page', 1)
    threads = paginator.get_page(page_number)

    return render(request, 'discussions.html', {
        'anime': anime,
        'threads': threads,
        'form': form,
        'episode_filter': episodes_filter,
    })


@transaction.atomic
def discussion_thread(request, thread_id):
    from apps.anime.models import DiscussionThread, DiscussionComment
    from apps.anime.forms import DiscussionCommentForm

    thread = get_object_or_404(DiscussionThread.objects.select_related('user', 'anime'), id=thread_id)
    DiscussionThread.objects.filter(id=thread.id).update(views=F('views') + 1)
    thread.refresh_from_db()

    comments = thread.comments.select_related('user').prefetch_related('replies').order_by('created_at')

    if request.method == 'POST' and request.user.is_authenticated:
        form = DiscussionCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.thread = thread
            comment.user = request.user
            parent_id = request.POST.get('parent')
            if parent_id:
                comment.parent_id = int(parent_id)
            comment.save()
            return redirect('discussion_thread', thread_id=thread.id)
    else:
        form = DiscussionCommentForm()

    return render(request, 'discussion_detail.html', {
        'thread': thread,
        'comments': comments,
        'form': form,
    })


@login_required
@transaction.atomic
def add_comment(request, thread_id):
    from apps.anime.models import DiscussionThread, DiscussionComment

    thread = get_object_or_404(DiscussionThread, id=thread_id)

    if request.method == 'POST':
        body = request.POST.get('body', '').strip()
        if body:
            DiscussionComment.objects.create(
                thread=thread,
                user=request.user,
                body=body,
                is_spoiler=request.POST.get('is_spoiler') == 'on',
                parent_id=request.POST.get('parent') or None,
            )
            UserActivity.objects.create(
                user=request.user,
                activity_type='COMMENT',
                description='Posted a comment',
            )
    return redirect('discussion_thread', thread_id=thread.id)


def search_view(request):
    q = request.GET.get('q', '').strip()
    page = int(request.GET.get('page', 1))
    results = []
    page_info = {}
    if q:
        try:
            data = anilist_client.search(search=q, page=page, per_page=24)
            results = data.get('Page', {}).get('media', [])
            page_info = data.get('Page', {}).get('pageInfo', {})
        except AniListError:
            pass
    return render(request, 'search.html', {
        'query': q, 'results': results, 'page_info': page_info, 'current_page': page,
    })


def search_json(request):
    from django.http import JsonResponse
    q = request.GET.get('q', '').strip()
    limit = int(request.GET.get('limit', 8))
    if len(q) < 2:
        return JsonResponse([], safe=False)
    try:
        data = anilist_client.search(search=q, page=1, per_page=min(limit, 20))
        results = data.get('Page', {}).get('media', [])
        items = [{
            'id': a['id'],
            'title': a.get('title', {}),
            'coverImage': a.get('coverImage', {}),
            'year': a.get('seasonYear'),
            'format': a.get('format', ''),
            'averageScore': a.get('averageScore'),
            'episodes': a.get('episodes'),
        } for a in results]
        return JsonResponse({'results': items}, safe=False)
    except AniListError:
        return JsonResponse({'results': []}, safe=False)


def character_view(request, character_id):
    try:
        data = anilist_client.get_character(int(character_id))
    except AniListError:
        return render(request, '404.html', status=404)
    char = data.get('Character', {})

    media_appearances = []
    for edge in char.get('media', {}).get('edges', []):
        node = edge.get('node', {})
        media_appearances.append({
            'id': node.get('id'),
            'title_romaji': node.get('title', {}).get('romaji', ''),
            'title_english': node.get('title', {}).get('english', ''),
            'cover': node.get('coverImage', {}).get('large', '') or node.get('coverImage', {}).get('medium', ''),
            'format': node.get('format', ''),
            'role': edge.get('characterRole', ''),
            'voice_actors': [{
                'id': va.get('id'),
                'name': va.get('name', {}).get('full', ''),
                'image': va.get('image', {}).get('medium', ''),
                'language': va.get('languageV2', ''),
            } for va in edge.get('voiceActors', [])],
        })

    return render(request, 'character.html', {
        'char': char,
        'media_appearances': media_appearances,
    })


def staff_view(request, staff_id):
    try:
        data = anilist_client.get_staff(int(staff_id))
    except AniListError:
        return render(request, '404.html', status=404)
    staff = data.get('Staff', {})
    return render(request, 'staff.html', {'staff': staff})


def seasonal_archive(request, year, season):
    season = season.upper()
    page = int(request.GET.get('page', 1))
    results = []
    page_info = {}
    try:
        data = anilist_client.get_popular_this_season(season=season, year=year, page=page, per_page=30)
        results = data.get('Page', {}).get('media', [])
        page_info = data.get('Page', {}).get('pageInfo', {})
    except AniListError:
        pass
    SEASONS = ['WINTER', 'SPRING', 'SUMMER', 'FALL']
    return render(request, 'seasonal.html', {
        'year': year, 'season': season, 'results': results,
        'page_info': page_info, 'current_page': page, 'seasons': SEASONS,
    })


@login_required
def notifications_json(request):
    from django.http import JsonResponse
    from apps.anime.models import Notification
    page = max(1, int(request.GET.get('page', 1)))
    limit = 50
    offset = (page - 1) * limit
    notifs = Notification.objects.filter(user=request.user).order_by('-created_at')[offset:offset + limit]
    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    total = Notification.objects.filter(user=request.user).count()
    data = [{
        'id': n.id, 'title': n.title, 'message': n.message,
        'url': n.url, 'is_read': n.is_read,
        'notification_type': n.notification_type,
        'created_at': n.created_at.isoformat(),
    } for n in notifs]
    return JsonResponse({
        'notifications': data, 'unread_count': unread_count,
        'total': total, 'page': page, 'has_more': total > offset + limit,
    })


@login_required
def mark_notification_read(request, notif_id):
    from django.http import JsonResponse
    from apps.anime.models import Notification
    Notification.objects.filter(id=notif_id, user=request.user).update(is_read=True)
    return JsonResponse({'ok': True})


@login_required
def mark_all_read(request):
    from django.http import JsonResponse
    from apps.anime.models import Notification
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'ok': True})


@login_required
def notification_list(request):
    from apps.anime.models import Notification
    from django.core.paginator import Paginator
    notif_qs = Notification.objects.filter(user=request.user).order_by('-created_at')
    paginator = Paginator(notif_qs, 30)
    page = request.GET.get('page', 1)
    notifications = paginator.get_page(page)
    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    return render(request, 'notification_list.html', {
        'notifications': notifications,
        'unread_count': unread_count,
        'paginator': paginator,
    })


@login_required
def user_settings(request):
    logger = logging.getLogger(__name__)
    user = request.user
    ok = True
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        if username and username != user.username:
            if get_user_model().objects.filter(username=username).exclude(pk=user.pk).exists():
                messages.error(request, 'Username already taken')
                ok = False
            else:
                user.username = username
        user.bio = request.POST.get('bio', '')

        from PIL import Image
        from apps.core.utils import validate_uploaded_image
        if 'avatar_file' in request.FILES:
            f = request.FILES['avatar_file']
            err = validate_uploaded_image(f)
            if err:
                messages.error(request, err)
                ok = False
            else:
                old_name = user.avatar.name if user.avatar and user.avatar.name else None
                try:
                    img = Image.open(f)
                    img.verify()
                    f.seek(0)
                    user.avatar.save(f'avatar_{uuid4().hex}', f)
                except Exception as exc:
                    logger.exception('Avatar upload failed: %s | content_type=%s | size=%s',
                                     exc, getattr(f, 'content_type', '?'), getattr(f, 'size', '?'))
                    messages.error(request, 'Failed to upload avatar.')
                    ok = False
                else:
                    if old_name:
                        try:
                            user.avatar.storage.delete(old_name)
                        except Exception:
                            logger.warning('Failed to delete old avatar: %s', old_name)

        if 'cover_file' in request.FILES:
            f = request.FILES['cover_file']
            err = validate_uploaded_image(f)
            if err:
                messages.error(request, err)
                ok = False
            else:
                old_name = user.cover_image.name if user.cover_image and user.cover_image.name else None
                try:
                    img = Image.open(f)
                    img.verify()
                    f.seek(0)
                    user.cover_image.save(f'cover_{uuid4().hex}', f)
                except Exception as exc:
                    logger.exception('Cover upload failed: %s | content_type=%s | size=%s',
                                     exc, getattr(f, 'content_type', '?'), getattr(f, 'size', '?'))
                    messages.error(request, 'Failed to upload cover image.')
                    ok = False
                else:
                    if old_name:
                        try:
                            user.cover_image.storage.delete(old_name)
                        except Exception:
                            logger.warning('Failed to delete old cover: %s', old_name)

        user.timezone = request.POST.get('timezone', 'UTC')
        user.notify_new_episodes = request.POST.get('notify_new_episodes') == 'on'
        user.notify_airing = request.POST.get('notify_airing') == 'on'
        email = request.POST.get('email', '').strip()
        if email:
            user.email = email
        user.save()
        if ok:
            messages.success(request, 'Settings saved!')
        return redirect('user_settings')
    return render(request, 'user_settings.html', {'user': user})


def sitemap_view(request):
    from django.http import HttpResponse
    from apps.anime.models import Anime
    from datetime import date
    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    lines.append('  <url><loc>https://anipulse.com/</loc><priority>1.0</priority></url>')
    lines.append('  <url><loc>https://anipulse.com/discover/</loc><priority>0.8</priority></url>')
    lines.append('  <url><loc>https://anipulse.com/battles/</loc><priority>0.6</priority></url>')
    lines.append('  <url><loc>https://anipulse.com/social/</loc><priority>0.6</priority></url>')
    lines.append('  <url><loc>https://anipulse.com/calendar/</loc><priority>0.7</priority></url>')
    for anime in Anime.objects.filter(status__in=['FINISHED', 'RELEASING']).order_by('-popularity')[:500]:
        lines.append(f'  <url><loc>https://anipulse.com/anime/{anime.anilist_id}/</loc><priority>0.5</priority></url>')
    lines.append('</urlset>')
    return HttpResponse('\n'.join(lines), content_type='application/xml')


@login_required
def comment_list(request):
    from django.http import JsonResponse
    from django.contrib.contenttypes.models import ContentType
    ctype = request.GET.get('ctype')
    oid = request.GET.get('oid')
    if not ctype or not oid:
        return JsonResponse({'error': 'Missing params'}, status=400)
    try:
        app_label, model = ctype.split('.')
        ct = ContentType.objects.get_by_natural_key(app_label, model)
        obj = ct.get_object_for_this_type(id=int(oid))
    except Exception:
        return JsonResponse({'error': 'Invalid content type'}, status=400)

    comments = Comment.objects.filter(
        content_type=ct, object_id=obj.id, parent__isnull=True
    ).select_related('user').prefetch_related(
        'replies__user', 'replies__replies__user',
        'likes', 'replies__likes', 'replies__replies__likes',
    ).order_by('created_at')

    liked_ids = set()
    if request.user.is_authenticated:
        all_ids = set()
        for c in comments:
            all_ids.add(c.id)
            for r in list(c.replies.all()):
                all_ids.add(r.id)
                for rr in list(r.replies.all()):
                    all_ids.add(rr.id)
        liked_ids = set(CommentLike.objects.filter(
            user=request.user, comment_id__in=all_ids
        ).values_list('comment_id', flat=True))

    def serialize(c, depth=0):
        replies_list = list(c.replies.all()) if depth < 2 else []
        return {
            'id': c.id,
            'user': c.user.username,
            'user_id': c.user.id,
            'avatar': c.user.avatar.url if c.user.avatar else '',
            'body': c.body,
            'is_spoiler': c.is_spoiler,
            'is_edited': c.is_edited,
            'depth': depth,
            'likes': c.like_count,
            'liked': c.id in liked_ids,
            'can_edit': c.can_edit(request.user) if request.user.is_authenticated else False,
            'created_at': c.created_at.isoformat(),
            'replies': [serialize(r, depth + 1) for r in replies_list[:3]] if depth < 2 else [],
            'has_more': len(replies_list) > 3 if depth < 2 else False,
        }
    data = [serialize(c) for c in comments]
    return JsonResponse({'comments': data})


@login_required
@transaction.atomic
@ratelimit(key='ip', rate='10/m', method='POST', block=False)
def comment_create(request):
    from django.http import JsonResponse
    from django.contrib.contenttypes.models import ContentType
    if getattr(request, 'limited', False):
        return JsonResponse({'error': 'Too many comments. Slow down.'}, status=429)

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    body = request.POST.get('body', '').strip()
    if not body or len(body) > 2000:
        return JsonResponse({'error': 'Invalid body'}, status=400)

    if len(body) < 2:
        return JsonResponse({'error': 'Comment too short'}, status=400)

    ctype = request.POST.get('ctype')
    oid = request.POST.get('oid')
    parent_id = request.POST.get('parent')

    if not ctype or not oid:
        return JsonResponse({'error': 'Missing content type'}, status=400)

    try:
        app_label, model = ctype.split('.')
        ct = ContentType.objects.get_by_natural_key(app_label, model)
        obj = ct.get_object_for_this_type(id=int(oid))
    except Exception:
        return JsonResponse({'error': 'Invalid content'}, status=400)

    parent = None
    if parent_id:
        try:
            parent = Comment.objects.get(id=int(parent_id))
            if parent.depth >= Comment.MAX_DEPTH - 1:
                return JsonResponse({'error': 'Max reply depth reached'}, status=400)
        except (Comment.DoesNotExist, ValueError):
            pass

    try:
        comment = Comment.objects.create(
            user=request.user,
            body=body,
            parent=parent,
            content_type=ct,
            object_id=obj.id,
            is_spoiler=request.POST.get('spoiler') == '1',
        )
        from apps.core.signals import engine
        engine.award_xp(request.user, 'comment')
        UserActivity.objects.create(
            user=request.user,
            activity_type='COMMENT',
            description='Posted a comment',
        )
        if hasattr(comment.content_object, 'user') and comment.content_object.user != request.user:
            _create_notification(comment.content_object.user, f'{request.user.username} commented on your post', url=comment.content_object.get_absolute_url() if hasattr(comment.content_object, 'get_absolute_url') else '/', ntype='COMMENT')
    except Exception:
        return JsonResponse({'error': 'Failed to create comment'}, status=500)

    return JsonResponse({
        'id': comment.id,
        'user': comment.user.username,
        'user_id': comment.user.id,
        'avatar': comment.user.avatar.url if comment.user.avatar else '',
        'body': comment.body,
        'is_spoiler': comment.is_spoiler,
        'depth': comment.depth,
        'likes': 0,
        'liked': False,
        'can_edit': True,
        'created_at': comment.created_at.isoformat(),
        'replies': [],
        'has_more': False,
    })


@login_required
@transaction.atomic
def comment_edit(request, comment_id):
    from django.http import JsonResponse
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    comment = get_object_or_404(Comment, id=comment_id)
    if not comment.can_edit(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    body = request.POST.get('body', '').strip()
    if not body or len(body) > 2000:
        return JsonResponse({'error': 'Invalid body'}, status=400)

    comment.body = body
    comment.is_edited = True
    comment.save(update_fields=['body', 'is_edited', 'updated_at'])
    return JsonResponse({'ok': True, 'body': comment.body, 'is_edited': True})


@login_required
@transaction.atomic
def comment_delete(request, comment_id):
    from django.http import JsonResponse
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    comment = get_object_or_404(Comment, id=comment_id)
    if not comment.can_edit(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    comment.body = '[deleted]'
    comment.is_edited = False
    comment.save(update_fields=['body', 'is_edited'])
    return JsonResponse({'ok': True})


@login_required
@transaction.atomic
def comment_like(request, comment_id):
    from django.http import JsonResponse
    from django.db.models import F
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    comment = get_object_or_404(Comment, id=comment_id)
    like, created = CommentLike.objects.get_or_create(comment=comment, user=request.user)
    if created:
        from apps.core.signals import engine
        engine.award_xp(request.user, 'like_review')
        UserActivity.objects.create(
            user=request.user,
            activity_type='LIKE',
            description='Liked a comment',
        )
        return JsonResponse({'liked': True, 'likes': comment.like_count + 1})
    else:
        like.delete()
        return JsonResponse({'liked': False, 'likes': max(comment.like_count - 1, 0)})


@login_required
def friend_activity(request):
    followed = UserFollow.objects.filter(follower=request.user).values_list('following_id', flat=True)
    activities = UserActivity.objects.filter(user_id__in=list(followed) + [request.user.id]).select_related('user', 'anime')[:30]
    return render(request, 'friend_activity.html', {'activities': activities})


@login_required
def import_anilist(request):
    from django.http import JsonResponse
    from apps.anime.services.anilist import anilist_client, AniListError
    from apps.anime.services.sync import sync_anime_from_anilist

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        if not username:
            messages.error(request, 'Enter an AniList username.')
            return redirect('import_anilist')
        try:
            query = '''
            query($name: String) {
              User(name: $name) {
                id name
                statistics { anime { count episodesWatched minutesWatched meanScore } }
              }
            }
            '''
            import httpx
            resp = httpx.post('https://graphql.anilist.co', json={'query': query, 'variables': {'name': username}}, timeout=15)
            user_data = resp.json()
            if 'errors' in user_data:
                messages.error(request, 'AniList user not found.')
                return redirect('import_anilist')
            user_info = user_data.get('data', {}).get('User', {})
            stats = user_info.get('statistics', {}).get('anime', {})

            # Fetch their anime list
            list_query = '''
            query($name: String, $page: Int) {
              Page(page: $page, perPage: 50) {
                pageInfo { hasNextPage }
                mediaList(userName: $name, type: ANIME, sort: UPDATED_TIME_DESC) {
                  mediaId
                  status
                  score
                  progress
                  startedAt { year month day }
                  completedAt { year month day }
                  media { id title { romaji english } coverImage { large medium } format status episodes duration averageScore genres }
                }
              }
            }
            '''
            page = 1
            imported = 0
            while True:
                resp = httpx.post('https://graphql.anilist.co', json={'query': list_query, 'variables': {'name': username, 'page': page}}, timeout=15)
                data = resp.json()
                entries = data.get('data', {}).get('Page', {}).get('mediaList', [])
                if not entries:
                    break
                for entry in entries:
                    if not entry.get('media'):
                        continue
                    media = entry['media']
                    anime = sync_anime_from_anilist(media)
                    status_map = {
                        'CURRENT': 'WATCHING', 'COMPLETED': 'COMPLETED',
                        'PAUSED': 'PAUSED', 'DROPPED': 'DROPPED', 'PLANNING': 'PLANNING',
                    }
                    status = status_map.get(entry.get('status', ''), 'PLANNING')
                    score = entry.get('score')
                    if score and isinstance(score, (int, float)):
                        score = score / 10 if score > 10 else score
                    WatchlistEntry.objects.update_or_create(
                        user=request.user, anime=anime,
                        defaults={
                            'status': status,
                            'score': score,
                            'episodes_watched': entry.get('progress', 0),
                        }
                    )
                    imported += 1
                if not data.get('data', {}).get('Page', {}).get('pageInfo', {}).get('hasNextPage'):
                    break
                page += 1
            # Import reviews
            review_query = '''
            query($userId: Int, $page: Int) {
              Page(page: $page, perPage: 50) {
                pageInfo { hasNextPage }
                reviews(userId: $userId, sort: CREATED_ID_DESC) {
                  id
                  score
                  summary
                  body(asHtml: false)
                  createdAt
                  media { id title { romaji english } coverImage { large medium } format status episodes duration averageScore genres }
                }
              }
            }
            '''
            page = 1
            reviews_imported = 0
            user_id = user_info.get('id')
            while True:
                resp = httpx.post('https://graphql.anilist.co', json={'query': review_query, 'variables': {'userId': user_id, 'page': page}}, timeout=15)
                data = resp.json()
                entries = data.get('data', {}).get('Page', {}).get('reviews', [])
                if not entries:
                    break
                for entry in entries:
                    media = entry.get('media')
                    if not media:
                        continue
                    from apps.anime.models import Review
                    anime = sync_anime_from_anilist(media)
                    score = entry.get('score')
                    if score and isinstance(score, (int, float)):
                        score = round(score / 10) if score > 10 else round(score)
                    body = entry.get('body', '') or ''
                    summary = entry.get('summary', '') or ''
                    Review.objects.update_or_create(
                        anime=anime, user=request.user,
                        defaults={
                            'rating': max(1, min(10, score or 5)),
                            'title': surrogatefree(summary[:200]),
                            'body': surrogatefree(body),
                            'anilist_review_id': entry['id'],
                        }
                    )
                    reviews_imported += 1
                if not data.get('data', {}).get('Page', {}).get('pageInfo', {}).get('hasNextPage'):
                    break
                page += 1
            messages.success(request, f'Imported {imported} anime and {reviews_imported} reviews from {username}!')
            return redirect('watchlist')
        except Exception as e:
            messages.error(request, f'Import failed: {e}')
            return redirect('import_anilist')
    return render(request, 'import_anilist.html')


@login_required
def bulk_update_watchlist(request):
    if request.method == 'POST':
        entry_ids = request.POST.getlist('entry_ids')
        action = request.POST.get('bulk_action')
        entries = WatchlistEntry.objects.filter(id__in=entry_ids, user=request.user)
        if action == 'delete':
            entries.delete()
            messages.success(request, f'Deleted {len(entry_ids)} entries.')
        elif action in dict(WatchlistEntry.Status.choices):
            entries.update(status=action)
            messages.success(request, f'Updated {len(entry_ids)} entries to {dict(WatchlistEntry.Status.choices)[action]}.')
        return redirect('watchlist')
    return redirect('watchlist')


@login_required
def toggle_character_favorite(request, character_id):
    from django.http import JsonResponse
    from apps.anime.models import CharacterFavorite
    name = request.GET.get('name', '')
    image = request.GET.get('image', '')
    fav, created = CharacterFavorite.objects.get_or_create(
        user=request.user, character_id=character_id,
        defaults={'character_name': name, 'character_image': image},
    )
    if not created:
        fav.delete()
        return JsonResponse({'favorited': False})
    return JsonResponse({'favorited': True})


@login_required
def check_character_favorite(request, character_id):
    from django.http import JsonResponse
    from apps.anime.models import CharacterFavorite
    exists = CharacterFavorite.objects.filter(user=request.user, character_id=character_id).exists()
    return JsonResponse({'favorited': exists})


@login_required
def toggle_staff_favorite(request, staff_id):
    from django.http import JsonResponse
    from apps.anime.models import StaffFavorite
    name = request.GET.get('name', '')
    image = request.GET.get('image', '')
    fav, created = StaffFavorite.objects.get_or_create(
        user=request.user, staff_id=staff_id,
        defaults={'staff_name': name, 'staff_image': image},
    )
    if not created:
        fav.delete()
        return JsonResponse({'favorited': False})
    return JsonResponse({'favorited': True})


@login_required
def check_staff_favorite(request, staff_id):
    from django.http import JsonResponse
    from apps.anime.models import StaffFavorite
    exists = StaffFavorite.objects.filter(user=request.user, staff_id=staff_id).exists()
    return JsonResponse({'favorited': exists})

