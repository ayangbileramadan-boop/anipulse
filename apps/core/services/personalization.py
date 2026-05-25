import logging
from collections import Counter, defaultdict
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Q, Avg, Prefetch
from django.utils.timezone import now

from apps.anime.models import Anime, Genre
from apps.watchlist.models import WatchlistEntry

logger = logging.getLogger(__name__)

CACHE_TTL = 60 * 60  # 1 hour


class PersonalizationEngine:
    """
    Cached personalization engine.
    Pre-computes user affinity profiles and serves personalized
    recommendations, continue-watching, and discovery sections.
    """

    # ─── Public API ─────────────────────────────────────

    def get_homepage_sections(self, user):
        """Return personalized homepage sections for a user."""
        if user.is_authenticated:
            return self._personalized_homepage(user)
        return self._anonymous_homepage()

    def get_recommendations(self, user, limit=20):
        """Personalized anime recommendations with caching."""
        if not user.is_authenticated:
            return self._trending_fallback(limit)

        cache_key = f"recs:user:{user.id}:{limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        recs = self._compute_recommendations(user, limit)
        cache.set(cache_key, recs, CACHE_TTL)
        return recs

    def get_continue_watching(self, user, limit=10):
        """Watching anime with next unwatched episode."""
        if not user.is_authenticated:
            return []

        cache_key = f"continue:user:{user.id}:{limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        entries = WatchlistEntry.objects.filter(
            user=user,
            status='WATCHING',
        ).select_related('anime').order_by('-updated_at')[:limit]

        result = []
        for entry in entries:
            anime = entry.anime
            if not anime or not anime.episodes:
                continue
            next_ep = (entry.episodes_watched or 0) + 1
            if next_ep <= (anime.episodes or 999):
                result.append({
                    'id': anime.anilist_id,
                    'title': anime.display_title,
'image': anime.cover_image_large or anime.cover_image_medium,
                    'episode': next_ep,
                    'total': anime.episodes,
                    'progress': round((entry.episodes_watched or 0) / anime.episodes * 100),
                })

        cache.set(cache_key, result, CACHE_TTL // 2)
        return result

    def get_genre_affinity(self, user):
        """Compute user's genre affinity profile (0-1 per genre)."""
        if not user.is_authenticated:
            return {}

        cache_key = f"affinity:user:{user.id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        entries = WatchlistEntry.objects.filter(
            user=user,
            status__in=['COMPLETED', 'WATCHING'],
        ).select_related('anime').prefetch_related('anime__genres')

        genre_scores = defaultdict(float)
        genre_counts = defaultdict(int)

        for entry in entries:
            score = (entry.score or 0) / 10.0  # Normalize to 0-1
            if entry.status == 'COMPLETED':
                score *= 1.2  # Completed entries weighted higher
            completion = 1.0
            anime = entry.anime
            if anime and anime.episodes:
                completion = min((entry.episodes_watched or 0) / anime.episodes, 1.0)
            score *= (0.5 + 0.5 * completion)

            if anime:
                for genre in anime.genres.all():
                    genre_scores[genre.name] += score
                    genre_counts[genre.name] += 1

        affinity = {}
        for name, total in genre_scores.items():
            count = genre_counts[name]
            avg = total / max(count, 1)
            # Boost by frequency of watch
            frequency_boost = min(count / 3, 1.0) * 0.3
            affinity[name] = min(avg + frequency_boost, 1.0)

        cache.set(cache_key, affinity, CACHE_TTL * 2)
        return dict(affinity)

    # ─── Celery-friendly pre-computation ────────────────

    def precompute_all(self):
        """Precompute profiles for all active users — call from Celery."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        active_users = User.objects.filter(
            watchlist__isnull=False,
        ).distinct().iterator()

        for user in active_users:
            try:
                self._compute_recommendations(user, 20)
                self.get_genre_affinity(user)
                self.get_continue_watching(user)
            except Exception as e:
                logger.error("Precompute failed for user %s: %s", user.id, e)

    # ─── Private: Personalization Logic ─────────────────

    def _personalized_homepage(self, user):
        affinity = self.get_genre_affinity(user)
        continue_watching = self.get_continue_watching(user)

        sections = []

        if continue_watching:
            sections.append({
                'key': 'continue_watching',
                'title': 'Continue Watching',
                'items': continue_watching,
            })

        # "Because you liked [top genre]..."
        if affinity:
            top_genre = max(affinity, key=affinity.get)
            similar = self._anime_by_genre(top_genre, exclude_user=user, limit=10)
            if similar:
                sections.append({
                    'key': 'genre_affinity',
                    'title': f"Because you liked {top_genre}",
                    'items': similar,
                })

            # Top 3 genres mix
            top3 = sorted(affinity, key=affinity.get, reverse=True)[:3]
            if len(top3) >= 2:
                mixed = self._anime_by_genres(top3, exclude_user=user, limit=10)
                if mixed:
                    sections.append({
                        'key': 'mixed_affinity',
                        'title': 'More from your favorite genres',
                        'items': mixed,
                    })

        # Popular this season
        season = self._current_season()
        seasonal_hits = Anime.objects.filter(
            season=season['season'], season_year=season['year'],
            is_adult=False,
        ).exclude(
            watchlist_entries__user=user,
        ).order_by('-average_score', '-popularity')[:10]
        if seasonal_hits:
            sections.append({
                'key': 'seasonal',
                'title': f"Popular This {season['season'].title()}",
                'items': [self._anime_to_dict(a) for a in seasonal_hits],
            })

        # Trending fallback
        if not sections:
            sections = self._anonymous_homepage()

        return sections

    def _anonymous_homepage(self):
        return [{
            'key': 'trending',
            'title': 'Trending Now',
            'items': self._trending_fallback(10),
        }]

    def _compute_recommendations(self, user, limit):
        affinity = self.get_genre_affinity(user)
        if not affinity:
            return self._trending_fallback(limit)

        watched_ids = WatchlistEntry.objects.filter(
            user=user
        ).values_list('anime_id', flat=True)

        # Weighted genre scoring
        scored = defaultdict(float)
        anime_qs = Anime.objects.filter(
            genres__name__in=list(affinity.keys()),
            is_adult=False,
        ).exclude(
            id__in=list(watched_ids),
        ).prefetch_related('genres').distinct()

        for anime in anime_qs:
            score = 0
            genre_count = 0
            for genre in anime.genres.all():
                if genre.name in affinity:
                    score += affinity[genre.name]
                    genre_count += 1
            if genre_count:
                avg_affinity = score / genre_count
                genre_diversity = min(genre_count / 3, 1.0)
                final = avg_affinity * 0.6 + genre_diversity * 0.2 + (anime.popularity or 0) / 1e6 * 0.2
                scored[anime.anilist_id] = (final, anime)

        sorted_ids = sorted(scored.keys(), key=lambda k: scored[k][0], reverse=True)[:limit]
        return [self._anime_to_dict(scored[sid][1]) for sid in sorted_ids]

    def _anime_by_genre(self, genre_name, exclude_user=None, limit=10):
        qs = Anime.objects.filter(
            genres__name=genre_name,
            is_adult=False,
        ).order_by('-average_score', '-popularity')[:limit]
        if exclude_user and exclude_user.is_authenticated:
            watched = WatchlistEntry.objects.filter(
                user=exclude_user
            ).values_list('anime_id', flat=True)
            qs = qs.exclude(id__in=list(watched))
        return [self._anime_to_dict(a) for a in qs[:limit]]

    def _anime_by_genres(self, genre_names, exclude_user=None, limit=10):
        qs = Anime.objects.filter(
            genres__name__in=genre_names,
            is_adult=False,
        ).annotate(
            genre_match=Count('genres', filter=Q(genres__name__in=genre_names))
        ).filter(
            genre_match__gte=2
        ).order_by('-average_score', '-popularity')
        if exclude_user and exclude_user.is_authenticated:
            watched = WatchlistEntry.objects.filter(
                user=exclude_user
            ).values_list('anime_id', flat=True)
            qs = qs.exclude(id__in=list(watched))
        return [self._anime_to_dict(a) for a in qs[:limit]]

    def _trending_fallback(self, limit):
        qs = Anime.objects.filter(
            is_adult=False,
        ).order_by('-trending', '-popularity')[:limit]
        return [self._anime_to_dict(a) for a in qs]

    @staticmethod
    def _current_season():
        month = now().month
        if month in (12, 1, 2): s = 'winter'
        elif month in (3, 4, 5): s = 'spring'
        elif month in (6, 7, 8): s = 'summer'
        else: s = 'fall'
        year = now().year
        if month == 12: year += 1
        return {'season': s, 'year': year}

    @staticmethod
    def _anime_to_dict(anime):
        return {
            'id': anime.anilist_id,
            'title': anime.display_title,
            'image': anime.cover_image_large or anime.cover_image_medium,
            'score': anime.average_score / 10 if anime.average_score else None,
            'episodes': anime.episodes,
            'status': anime.status,
            'format': anime.format,
        }
