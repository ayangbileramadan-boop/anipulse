import time
import logging
from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=120, name='anime.sync_trending')
def sync_trending_anime(self):
    """Sync top-50 trending anime into local DB. Scheduled hourly."""
    from apps.anime.services.anilist import anilist_client
    from apps.anime.services.sync import sync_anime_from_anilist
    try:
        data = anilist_client.get_trending(page=1, per_page=50)
        media_list = data['Page']['media']
        synced = 0
        for media in media_list:
            sync_anime_from_anilist(media)
            synced += 1
        logger.info("sync_trending_anime: synced %d anime", synced)
        return {'synced': synced}
    except Exception as exc:
        logger.error("sync_trending_anime failed: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60, name='anime.sync_seasonal')
def sync_seasonal_anime(self):
    """Sync current season popular anime. Scheduled every 6 hours."""
    from apps.anime.services.anilist import anilist_client
    from apps.anime.services.sync import sync_anime_from_anilist
    from apps.core.utils import get_current_season
    try:
        season, year = get_current_season()
        data = anilist_client.get_popular_this_season(season=season, year=year, per_page=50)
        media_list = data['Page']['media']
        for media in media_list:
            sync_anime_from_anilist(media)
        logger.info("sync_seasonal_anime: synced %d anime (%s %d)", len(media_list), season, year)
        return {'synced': len(media_list), 'season': season, 'year': year}
    except Exception as exc:
        logger.error("sync_seasonal_anime failed: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=30, name='anime.fetch_airing_schedule')
def fetch_airing_schedule(self):
    """Fetch this week's airing schedule and cache it. Scheduled every 15 min."""
    from apps.anime.services.anilist import anilist_client
    try:
        now = int(time.time())
        week_end = now + (7 * 24 * 60 * 60)
        data = anilist_client.get_airing_schedule(week_start=now, week_end=week_end)
        count = len(data['Page']['airingSchedules'])
        logger.info("fetch_airing_schedule: fetched %d entries", count)
        return {'count': count}
    except Exception as exc:
        logger.error("fetch_airing_schedule failed: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=60, name='notifications.check_airing')
def check_airing_episodes(self):
    """Check for episodes airing in the next hour and notify users. Runs every 30 min."""
    from apps.core.notifications import check_airing_episodes as _check
    try:
        _check()
        return {'status': 'ok'}
    except Exception as exc:
        logger.error("check_airing_episodes failed: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=1, default_retry_delay=300, name='notifications.weekly_digest')
def send_weekly_digest(self):
    """Send weekly digest to opted-in users. Runs every Monday at 9 AM."""
    from apps.core.notifications import send_weekly_digest as _digest
    try:
        _digest()
        return {'status': 'ok'}
    except Exception as exc:
        logger.error("send_weekly_digest failed: %s", exc)
        raise self.retry(exc=exc)
