import logging
from django.utils import timezone
from django.utils.text import slugify

from apps.anime.models import Anime, Genre, Studio, Tag, AnimeTag, ExternalLink
from apps.core.utils import parse_anilist_date, surrogatefree, unix_to_datetime

logger = logging.getLogger(__name__)


def _make_unique_slug(base_slug: str, anilist_id: int) -> str:
    slug = base_slug
    if Anime.objects.filter(slug=slug).exclude(anilist_id=anilist_id).exists():
        slug = f"{base_slug}-{anilist_id}"
    return slug


def sync_anime_from_anilist(data: dict) -> Anime:
    """
    Upsert one anime record from AniList media payload.
    Handles genres, tags, studios, and external links atomically.
    Returns the saved Anime instance.
    """
    title = data.get('title', {})
    title_romaji = title.get('romaji', '') or ''
    title_english = title.get('english', '') or ''
    title_native = title.get('native', '') or ''

    slug_base = slugify(title_english or title_romaji)[:580]
    slug = _make_unique_slug(slug_base, data['id'])

    # Airing info
    next_airing = data.get('nextAiringEpisode') or {}
    next_at = unix_to_datetime(next_airing.get('airingAt'))
    next_ep = next_airing.get('episode')

    # Trailer
    trailer = data.get('trailer') or {}

    # Studios
    studios_data = (data.get('studios') or {}).get('nodes', [])

    defaults = {
        'title_romaji': surrogatefree(title_romaji),
        'title_english': surrogatefree(title_english),
        'title_native': surrogatefree(title_native),
        'slug': slug,
        'description': surrogatefree(data.get('description', '') or ''),
        'format': data.get('format', '') or '',
        'status': data.get('status', '') or '',
        'episodes': data.get('episodes'),
        'duration': data.get('duration'),
        'season': data.get('season', '') or '',
        'season_year': data.get('seasonYear'),
        'start_date': parse_anilist_date(data.get('startDate')),
        'end_date': parse_anilist_date(data.get('endDate')),
        'next_airing_episode': next_ep,
        'next_airing_at': next_at,
        'average_score': data.get('averageScore'),
        'mean_score': data.get('meanScore'),
        'popularity': data.get('popularity'),
        'trending': data.get('trending'),
        'favourites': data.get('favourites'),
        'cover_image_large': (data.get('coverImage') or {}).get('large', '') or '',
        'cover_image_medium': (data.get('coverImage') or {}).get('medium', '') or '',
        'cover_image_color': (data.get('coverImage') or {}).get('color', '') or '',
        'banner_image': data.get('bannerImage', '') or '',
        'is_adult': data.get('isAdult', False),
        'site_url': data.get('siteUrl', '') or '',
        'trailer_site': trailer.get('site', '') or '',
        'trailer_id': (trailer.get('id', '') or '').strip(),
        'trailer_thumbnail': trailer.get('thumbnail', '') or '',
        'last_synced_at': timezone.now(),
    }

    anime, created = Anime.objects.update_or_create(
        anilist_id=data['id'],
        defaults=defaults,
    )

    # Genres
    genre_names = data.get('genres', []) or []
    genre_objs = []
    for name in genre_names:
        g, _ = Genre.objects.get_or_create(name=name)
        genre_objs.append(g)
    anime.genres.set(genre_objs)

    # Tags
    tags_data = data.get('tags', []) or []
    AnimeTag.objects.filter(anime=anime).delete()
    for t in tags_data:
        tag, _ = Tag.objects.get_or_create(
            name=t['name'],
            defaults={'is_general_spoiler': t.get('isGeneralSpoiler', False)},
        )
        AnimeTag.objects.create(anime=anime, tag=tag, rank=t.get('rank', 0))

    # Studios
    studio_objs = []
    for s in studios_data:
        studio, _ = Studio.objects.get_or_create(
            anilist_id=s['id'],
            defaults={'name': s['name'], 'site_url': s.get('siteUrl', '')},
        )
        studio_objs.append(studio)
    anime.studios.set(studio_objs)

    # External links
    links_data = data.get('externalLinks', []) or []
    ExternalLink.objects.filter(anime=anime).delete()
    for link in links_data:
        ExternalLink.objects.create(
            anime=anime,
            site=link.get('site', ''),
            url=link.get('url', ''),
            icon=link.get('icon', '') or '',
            color=link.get('color', '') or '',
            language=link.get('language', '') or '',
        )

    action = 'Created' if created else 'Updated'
    logger.debug("%s anime: %s (AniList ID: %d)", action, anime.display_title, data['id'])
    return anime
