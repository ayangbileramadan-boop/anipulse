import time
import logging
from datetime import datetime, timezone

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Count, Q

from apps.anime.services.anilist import anilist_client, AniListError
from apps.anime.services.sync import sync_anime_from_anilist
from apps.watchlist.models import WatchlistEntry
from apps.watchlist.models import ACHIEVEMENT_DEFS
from apps.anime.models import Anime, Battle, BattleVote, TierList, TierListItem, SocialPost, SocialLike, UserFollow, UserActivity, Streak
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
    animepahe_url = f'https://animepahe.ru/search?q={quote(search_title)}' if search_title else ''

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
    for entry in WatchlistEntry.objects.filter(user=request.user, status__in=['WATCHING', 'COMPLETED']).select_related('anime'):
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

    entries = qs.order_by('-updated_at')

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


def profile_view(request, username):
    User = get_user_model()
    profile_user = get_object_or_404(User, username=username)
    is_me = request.user == profile_user if request.user.is_authenticated else False

    stats = {
        'watching': WatchlistEntry.objects.filter(user=profile_user, status='WATCHING').count(),
        'completed': WatchlistEntry.objects.filter(user=profile_user, status='COMPLETED').count(),
        'paused': WatchlistEntry.objects.filter(user=profile_user, status='PAUSED').count(),
        'dropped': WatchlistEntry.objects.filter(user=profile_user, status='DROPPED').count(),
        'planning': WatchlistEntry.objects.filter(user=profile_user, status='PLANNING').count(),
        'total': WatchlistEntry.objects.filter(user=profile_user).count(),
    }

    total_hours = 0
    for entry in WatchlistEntry.objects.filter(user=profile_user, status__in=['COMPLETED', 'WATCHING']).select_related('anime'):
        if entry.anime.episodes and entry.anime.duration:
            ep = entry.episodes_watched if entry.status == 'WATCHING' else entry.anime.episodes
            total_hours += (ep * entry.anime.duration) / 60

    streak = Streak.objects.filter(user=profile_user).first()

    game_engine = GamificationEngine()
    game_profile = game_engine.get_profile(profile_user)
    level_progress = game_profile.level_progress
    unlocked_badges = game_engine.get_unlocked_badges(profile_user)

    return render(request, 'profile.html', {
        'profile_user': profile_user,
        'is_me': is_me,
        'stats': stats,
        'total_watch_hours': round(total_hours, 1),
        'profile_streak': streak,
        'game_profile': game_profile,
        'level_progress': level_progress,
        'unlocked_badges': unlocked_badges,
    })


@login_required
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
def like_review(request, review_id):
    from apps.anime.models import Review
    review = get_object_or_404(Review, id=review_id)
    if review.user != request.user:
        review.likes += 1
        review.save()
        _create_notification(review.user, f'{request.user.username} liked your review',
                             url=f'/anime/{review.anime.anilist_id}/')
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
    data1 = None
    data2 = None

    if id1:
        try:
            result = anilist_client.get_anime_detail(int(id1))
            data1 = result.get('Media', {})
        except AniListError:
            pass

    if id2:
        try:
            result = anilist_client.get_anime_detail(int(id2))
            data2 = result.get('Media', {})
        except AniListError:
            pass

    return render(request, 'compare.html', {
        'data1': data1,
        'data2': data2,
        'id1': id1,
        'id2': id2,
    })


@login_required
def profile_edit(request):
    user = request.user
    if request.method == 'POST':
        user.bio = request.POST.get('bio', '')
        user.avatar = request.POST.get('avatar', '')
        user.cover_image = request.POST.get('cover_image', '')
        user.save()
        messages.success(request, 'Profile updated!')
        return redirect('profile', username=user.username)
    return render(request, 'profile_edit.html', {'user': user})


@login_required
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
    battles_qs = Battle.objects.filter(is_active=True).select_related('anime1', 'anime2', 'created_by')
    paginator = Paginator(battles_qs, 20)
    page_number = request.GET.get('page', 1)
    battles = paginator.get_page(page_number)
    return render(request, 'battles.html', {'battles': battles})


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
                Battle.objects.create(anime1=results[0], anime2=results[1], created_by=request.user, category=cat)
                messages.success(request, 'Battle created!')
                return redirect('battle_list')
        messages.error(request, 'Could not create battle. Try searching exact titles.')
    return render(request, 'battle_create.html')


@login_required
def battle_vote(request, battle_id):
    battle = get_object_or_404(Battle, id=battle_id, is_active=True)
    if request.method == 'POST':
        choice = request.POST.get('choice')
        if choice in ('1', '2'):
            vote, created = BattleVote.objects.get_or_create(battle=battle, user=request.user, defaults={'choice': int(choice)})
            if not created:
                vote.choice = int(choice)
                vote.save()
            else:
                if choice == '1':
                    battle.votes1 += 1
                else:
                    battle.votes2 += 1
                battle.save()
            UserActivity.objects.create(user=request.user, activity_type='BATTLE', description=f"Voted in {battle}")
        return redirect('battle_list')
    return redirect('battle_list')


def tier_list_list(request):
    tls_qs = TierList.objects.filter(is_public=True).select_related('user').prefetch_related('items__anime')
    paginator = Paginator(tls_qs, 24)
    page_number = request.GET.get('page', 1)
    tier_lists = paginator.get_page(page_number)
    return render(request, 'tierlists.html', {'tier_lists': tier_lists})


@login_required
def tier_list_create(request):
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        if title:
            import string, random
            slug = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
            tl = TierList.objects.create(user=request.user, title=title, slug=slug)
            return redirect('tier_list_view', slug=slug)
    return render(request, 'tierlist_create.html')


def tier_list_view(request, slug):
    tl = get_object_or_404(TierList, slug=slug, is_public=True)
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
    return render(request, 'tierlist_view.html', {'tier_list': tl, 'tiers': tiers, 'tier_cfg': tier_cfg})


@login_required
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


def social_feed(request):
    posts_qs = SocialPost.objects.filter(reply_to__isnull=True).select_related('user', 'anime').prefetch_related('liked_by')
    paginator = Paginator(posts_qs, 20)
    page_number = request.GET.get('page', 1)
    posts = paginator.get_page(page_number)
    return render(request, 'social_feed.html', {'posts': posts})


@login_required
def social_create_post(request):
    if request.method == 'POST':
        body = request.POST.get('body', '').strip()
        if body:
            post = SocialPost.objects.create(user=request.user, body=body)
            UserActivity.objects.create(user=request.user, activity_type='POST', description=body[:100])
            messages.success(request, 'Posted!')
        return redirect('social_feed')
    return redirect('social_feed')


@login_required
def social_like_post(request, post_id):
    post = get_object_or_404(SocialPost, id=post_id)
    like, created = SocialLike.objects.get_or_create(post=post, user=request.user)
    if not created:
        like.delete()
        post.likes = max(0, post.likes - 1)
    else:
        post.likes += 1
        if post.user != request.user:
            _create_notification(post.user, f'{request.user.username} liked your post',
                                 url='/social/')
    post.save()
    return redirect('social_feed')


@login_required
def social_follow(request, username):
    User = get_user_model()
    target = get_object_or_404(User, username=username)
    if target != request.user:
        follow, created = UserFollow.objects.get_or_create(follower=request.user, following=target)
        if not created:
            follow.delete()
        else:
            _create_notification(target, f'{request.user.username} started following you',
                                 url='/social/')
    return redirect('social_feed')


@login_required
def anime_wrapped(request):
    entries = WatchlistEntry.objects.filter(user=request.user).select_related('anime')
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
    ).select_related('anime')

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


def chat_ai(request):
    from django.http import JsonResponse
    import random, re

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


def _create_notification(user, title, message='', url=''):
    from apps.anime.models import Notification
    Notification.objects.create(user=user, title=title, message=message, url=url)


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


def discussion_thread(request, thread_id):
    from apps.anime.models import DiscussionThread, DiscussionComment
    from apps.anime.forms import DiscussionCommentForm

    thread = get_object_or_404(DiscussionThread.objects.select_related('user', 'anime'), id=thread_id)
    thread.views += 1
    thread.save(update_fields=['views'])

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
    if len(q) < 2:
        return JsonResponse([], safe=False)
    try:
        data = anilist_client.search(search=q, page=1, per_page=8)
        results = data.get('Page', {}).get('media', [])
        items = [{
            'id': a['id'],
            'title': a.get('title', {}).get('english') or a.get('title', {}).get('romaji', ''),
            'image': a.get('coverImage', {}).get('medium', ''),
            'year': a.get('seasonYear'),
            'format': a.get('format', ''),
        } for a in results]
        return JsonResponse(items, safe=False)
    except AniListError:
        return JsonResponse([], safe=False)


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
    notifs = Notification.objects.filter(user=request.user)[:20]
    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    data = [{
        'id': n.id, 'title': n.title, 'message': n.message,
        'url': n.url, 'is_read': n.is_read,
        'created_at': n.created_at.isoformat(),
    } for n in notifs]
    return JsonResponse({'notifications': data, 'unread_count': unread_count})


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
def user_settings(request):
    user = request.user
    if request.method == 'POST':
        user.bio = request.POST.get('bio', '')
        user.avatar = request.POST.get('avatar', '')
        user.cover_image = request.POST.get('cover_image', '')
        user.timezone = request.POST.get('timezone', 'UTC')
        user.notify_new_episodes = request.POST.get('notify_new_episodes') == 'on'
        user.notify_airing = request.POST.get('notify_airing') == 'on'
        email = request.POST.get('email', '').strip()
        if email:
            user.email = email
        user.save()
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
            messages.success(request, f'Imported {imported} anime from {username}!')
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

