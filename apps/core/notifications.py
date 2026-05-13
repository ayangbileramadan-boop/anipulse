import time
import logging
from datetime import datetime, timezone, timedelta

from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string

from apps.anime.services.anilist import anilist_client, AniListError
from apps.watchlist.models import WatchlistEntry
from apps.users.models import User

logger = logging.getLogger(__name__)


def check_airing_episodes():
    """
    Called by Celery task. Checks for episodes airing in the next hour
    and sends email notifications to users who have opted in.
    """
    now = int(time.time())
    one_hour = now + 3600

    try:
        data = anilist_client.get_airing_schedule(week_start=now, week_end=one_hour)
        schedules = data.get('Page', {}).get('airingSchedules', [])
    except AniListError as e:
        logger.error(f"Failed to fetch airing schedules: {e}")
        return

    if not schedules:
        logger.info("No episodes airing in the next hour")
        return

    users_to_notify = User.objects.filter(
        notify_new_episodes=True,
        email__isnull=False,
    ).exclude(email='')

    if not users_to_notify.exists():
        logger.info("No users opted in for notifications")
        return

    anilist_ids = set(
        WatchlistEntry.objects.filter(
            status__in=['WATCHING', 'PLANNING'],
        ).values_list('anime__anilist_id', flat=True)
    )

    relevant_schedules = [
        s for s in schedules
        if s.get('media', {}).get('id') in anilist_ids
    ]

    if not relevant_schedules:
        logger.info("No relevant episodes for user watchlists")
        return

    for schedule in relevant_schedules:
        media = schedule.get('media', {})
        anime_id = media.get('id')
        episode_num = schedule.get('episode', '?')
        title = media.get('title', {}).get('english') or media.get('title', {}).get('romaji', '')

        entries = WatchlistEntry.objects.filter(
            anime__anilist_id=anime_id,
            status__in=['WATCHING', 'PLANNING'],
        ).select_related('user')

        user_ids_notified = set()
        for entry in entries:
            user = entry.user
            if user.id in user_ids_notified or not user.notify_new_episodes or not user.email:
                continue
            user_ids_notified.add(user.id)

            try:
                send_episode_notification(user, title, episode_num, media)
                logger.info(f"Sent notification to {user.email} for {title} Ep {episode_num}")
            except Exception as e:
                logger.error(f"Failed to send email to {user.email}: {e}")


def send_episode_notification(user, title, episode_num, media):
    """Send a single episode notification email."""
    subject = f"{title} - Episode {episode_num} is airing soon!"

    cover = media.get('coverImage', {}).get('large', '') or media.get('coverImage', {}).get('medium', '')
    banner = media.get('bannerImage', '')
    description = media.get('description', '')

    context = {
        'username': user.username,
        'title': title,
        'episode': episode_num,
        'cover': cover,
        'banner': banner,
        'description': description[:200] if description else '',
        'site_url': media.get('siteUrl', ''),
        'settings_url': 'https://anipulse.com/notifications/',
    }

    html_message = render_to_string('emails/new_episode.html', context)
    plain_message = f"Hey {user.username}!\n\n{title} Episode {episode_num} is airing soon!\n\nCheck it out on AniList: {media.get('siteUrl', '')}\n\nManage notifications: https://anipulse.com/notifications/"

    send_mail(
        subject=subject,
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,
        fail_silently=False,
    )


def send_weekly_digest():
    """
    Called by Celery task weekly. Sends a digest of upcoming episodes
    for each user's watchlist.
    """
    users = User.objects.filter(
        notify_airing=True,
        email__isnull=False,
    ).exclude(email='')

    now = int(time.time())
    week_end = now + (7 * 24 * 60 * 60)

    try:
        data = anilist_client.get_airing_schedule(week_start=now, week_end=week_end)
        all_schedules = data.get('Page', {}).get('airingSchedules', [])
    except AniListError as e:
        logger.error(f"Failed to fetch airing schedules for digest: {e}")
        return

    for user in users:
        user_anime_ids = set(
            WatchlistEntry.objects.filter(
                user=user,
                status__in=['WATCHING', 'PLANNING'],
            ).values_list('anime__anilist_id', flat=True)
        )

        user_schedules = [
            s for s in all_schedules
            if s.get('media', {}).get('id') in user_anime_ids
        ][:10]

        if not user_schedules:
            continue

        try:
            send_digest_email(user, user_schedules)
            logger.info(f"Sent weekly digest to {user.email}")
        except Exception as e:
            logger.error(f"Failed to send digest to {user.email}: {e}")


def send_digest_email(user, schedules):
    """Send weekly digest email."""
    subject = "Your Weekly Anime Digest is here!"

    formatted_schedules = []
    for s in schedules:
        media = s.get('media', {})
        airing_time = datetime.fromtimestamp(s['airingAt'], tz=timezone.utc)
        formatted_schedules.append({
            'title': media.get('title', {}).get('english') or media.get('title', {}).get('romaji', ''),
            'episode': s.get('episode', '?'),
            'airing_at': airing_time,
            'cover': media.get('coverImage', {}).get('medium', ''),
            'anilist_id': media.get('id'),
        })

    context = {
        'username': user.username,
        'schedules': formatted_schedules,
        'settings_url': 'https://anipulse.com/notifications/',
    }

    html_message = render_to_string('emails/weekly_digest.html', context)
    plain_message = f"Hey {user.username}!\n\nHere are {len(formatted_schedules)} episodes airing this week from your watchlist.\n\nView them on AniPulse!"

    send_mail(
        subject=subject,
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,
        fail_silently=False,
    )
