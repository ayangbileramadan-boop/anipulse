import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in

from apps.anime.models import Review, Battle, BattleVote, UserFollow
from apps.watchlist.models import WatchlistEntry
from apps.core.models import UserProfile
from apps.core.services.gamification import GamificationEngine, XP_RATES
from apps.core.services.quests import progress_quest, generate_daily_quests

logger = logging.getLogger(__name__)

engine = GamificationEngine()


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    try:
        engine.award_xp(user, 'daily_login')
        generate_daily_quests(user)
    except Exception as e:
        logger.error(f"Login XP/quests failed for {user.id}: {e}")


@receiver(post_save, sender=WatchlistEntry)
def watchlist_entry_saved(sender, instance, created, **kwargs):
    try:
        if created:
            engine.award_xp(instance.user, 'add_to_watchlist')
            progress_quest(instance.user, 'daily_add')
        if instance.status == 'COMPLETED':
            if instance.episodes_watched and instance.anime.episodes:
                ep_xp = (instance.episodes_watched // 10) * XP_RATES['complete_episode']
                profile, _ = UserProfile.objects.get_or_create(user=instance.user)
                profile.total_xp = (profile.total_xp or 0) + ep_xp + XP_RATES['complete_anime']
                profile.save(update_fields=['total_xp'])
                engine.check_badges(instance.user)
                progress_quest(instance.user, 'weekly_complete')
                progress_quest(instance.user, 'daily_complete')
    except Exception as e:
        logger.error(f"XP award failed for watchlist {instance.id}: {e}")


@receiver(post_save, sender=Review)
def review_saved(sender, instance, created, **kwargs):
    if created:
        try:
            engine.award_xp(instance.user, 'add_review')
            progress_quest(instance.user, 'daily_review')
            progress_quest(instance.user, 'weekly_review')
        except Exception as e:
            logger.error(f"XP award failed for review {instance.id}: {e}")


@receiver(post_save, sender=Battle)
def battle_created(sender, instance, created, **kwargs):
    if created and instance.created_by:
        try:
            engine.award_xp(instance.created_by, 'create_battle')
        except Exception as e:
            logger.error(f"XP award failed for battle {instance.id}: {e}")


@receiver(post_save, sender=BattleVote)
def battle_vote_cast(sender, instance, created, **kwargs):
    if created:
        try:
            engine.award_xp(instance.user, 'vote_battle')
            progress_quest(instance.user, 'weekly_battle')
        except Exception as e:
            logger.error(f"XP award failed for vote {instance.id}: {e}")


@receiver(post_save, sender=UserFollow)
def user_followed(sender, instance, created, **kwargs):
    if created:
        try:
            engine.award_xp(instance.follower, 'daily_login')
        except Exception as e:
            logger.error(f"XP award failed for follow {instance.id}: {e}")
