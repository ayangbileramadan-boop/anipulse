from collections import defaultdict
from apps.anime.models import Anime
from apps.watchlist.models import WatchlistEntry


def get_recommendations_for_user(user, limit=12):
    """
    Content-based recommendation engine.
    
    Algorithm:
    1. Find all anime the user has watched/completed
    2. Weight genres by: user_score × completion_rate
    3. Return top-scored anime in weighted genres, excluding already-watched
    
    Cold start: return trending anime
    """
    watched_entries = (
        WatchlistEntry.objects
        .filter(
            user=user,
            status__in=[WatchlistEntry.Status.COMPLETED, WatchlistEntry.Status.WATCHING],
        )
        .select_related('anime')
        .prefetch_related('anime__genres')
    )

    if not watched_entries.exists():
        # Cold start: return trending
        return Anime.objects.filter(is_adult=False).order_by('-trending')[:limit]

    # Weight genres by score × completion
    genre_weights = defaultdict(float)
    for entry in watched_entries:
        score = entry.score if entry.score else 7.0
        max_ep = entry.anime.episodes if entry.anime.episodes else 1
        completion = min(entry.episodes_watched / max_ep, 1.0)
        weight = score * completion

        for genre in entry.anime.genres.all():
            genre_weights[genre.name] += weight

    # Sort genres by total weight, take top 5
    top_genres = sorted(genre_weights.keys(), key=lambda g: genre_weights[g], reverse=True)[:5]

    # Exclude already-watched anime
    seen_ids = WatchlistEntry.objects.filter(user=user).values_list('anime_id', flat=True)

    # Fetch matching anime
    recommendations = (
        Anime.objects
        .filter(genres__name__in=top_genres, is_adult=False)
        .exclude(id__in=seen_ids)
        .distinct()
        .order_by('-average_score', '-popularity')[:limit]
    )

    return recommendations
