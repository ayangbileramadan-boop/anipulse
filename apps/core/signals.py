import logging

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in

from apps.anime.models import Review, Battle, BattleVote, SocialPost, SocialLike, DiscussionComment, UserActivity
from apps.core.models import UserFollow
from apps.watchlist.models import WatchlistEntry
from apps.core.services.gamification import GamificationEngine
from apps.core.services.quests import progress_quest, generate_daily_quests

logger = logging.getLogger(__name__)

engine = GamificationEngine()

_processed = set()


def _mark_processed(instance):
    key = (instance._meta.label, instance.pk)
    _processed.add(key)
    return key


def _is_processed(key):
    return key in _processed


def _cleanup_processed(key):
    _processed.discard(key)


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    try:
        with transaction.atomic():
            engine.award_xp(user, 'daily_login')
            generate_daily_quests(user)
    except Exception as e:
        logger.error(f"Login XP/quests failed for user {user.id}: {e}")


@receiver(pre_save, sender=WatchlistEntry)
def watchlist_entry_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = WatchlistEntry.objects.get(pk=instance.pk)
            instance._old_status = old.status
            instance._old_episodes = old.episodes_watched
        except WatchlistEntry.DoesNotExist:
            pass


@receiver(post_save, sender=WatchlistEntry)
def watchlist_entry_saved(sender, instance, created, **kwargs):
    pkey = (instance._meta.label, instance.pk)
    already_processed = pkey in _processed
    _processed.add(pkey)
    if already_processed and not created:
        return

    try:
        with transaction.atomic():
            old_eps = getattr(instance, '_old_episodes', 0) or 0
            new_eps = max(instance.episodes_watched or 0, 0)
            eps_diff = new_eps - old_eps
            if eps_diff > 0:
                for _ in range(eps_diff):
                    engine.award_xp(instance.user, 'complete_episode')
                progress_quest(instance.user, 'daily_episode')

            is_newly_completed = (
                instance.status == 'COMPLETED' and
                not created and
                getattr(instance, '_old_status', None) != 'COMPLETED'
            )

            if created:
                engine.award_xp(instance.user, 'add_to_watchlist')
                progress_quest(instance.user, 'daily_add')

            if created and instance.status == 'COMPLETED':
                engine.award_xp(instance.user, 'complete_anime')
                progress_quest(instance.user, 'weekly_complete')
                progress_quest(instance.user, 'daily_complete')
            elif is_newly_completed:
                engine.award_xp(instance.user, 'complete_anime')
                progress_quest(instance.user, 'weekly_complete')
                progress_quest(instance.user, 'daily_complete')

    except Exception as e:
        logger.error(f"Watchlist signal error for {instance.id}: {e}")
    finally:
        _cleanup_processed(pkey)


@receiver(post_save, sender=Review)
def review_saved(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        with transaction.atomic():
            engine.award_xp(instance.user, 'add_review')
            progress_quest(instance.user, 'daily_review')
            progress_quest(instance.user, 'weekly_review')
    except Exception as e:
        logger.error(f"Review signal error for {instance.id}: {e}")


@receiver(post_save, sender=Battle)
def battle_created(sender, instance, created, **kwargs):
    if not created or not instance.created_by:
        return
    try:
        with transaction.atomic():
            engine.award_xp(instance.created_by, 'create_battle')
        from apps.feed.services import FeedBuilder
        builder = FeedBuilder(instance.created_by)
        builder.invalidate()
    except Exception as e:
        logger.error(f"Battle signal error for {instance.id}: {e}")


@receiver(post_save, sender=BattleVote)
def battle_vote_cast(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        with transaction.atomic():
            engine.award_xp(instance.user, 'vote_battle')
            progress_quest(instance.user, 'weekly_battle')
    except Exception as e:
        logger.error(f"Vote signal error for {instance.id}: {e}")


@receiver(post_save, sender=SocialPost)
def social_post_created(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        with transaction.atomic():
            engine.award_xp(instance.user, 'create_post')
    except Exception as e:
        logger.error(f"Social post signal error for {instance.id}: {e}")


@receiver(post_save, sender=SocialLike)
def social_like_created(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        with transaction.atomic():
            engine.award_xp(instance.user, 'like_post')
    except Exception as e:
        logger.error(f"Social like signal error for {instance.id}: {e}")


@receiver(post_save, sender=DiscussionComment)
def discussion_comment_created(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        with transaction.atomic():
            engine.award_xp(instance.user, 'comment')
    except Exception as e:
        logger.error(f"Comment signal error for {instance.id}: {e}")


@receiver(post_save, sender=UserFollow)
def user_followed(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        with transaction.atomic():
            engine.award_xp(instance.follower, 'share_activity')
    except Exception as e:
        logger.error(f"Follow signal error for {instance.id}: {e}")


@receiver(post_save, sender=SocialPost, weak=False)
def invalidate_feed_on_post(sender, instance, created, **kwargs):
    if not created:
        return
    from apps.feed.services import FeedBuilder
    try:
        builder = FeedBuilder(instance.user)
        builder.invalidate()
        if instance.reply_to and instance.reply_to.user:
            builder2 = FeedBuilder(instance.reply_to.user)
            builder2.invalidate()
    except Exception as e:
        logger.error(f"Feed invalidation error (post): {e}")


@receiver(post_save, sender=SocialLike, weak=False)
def invalidate_feed_on_like(sender, instance, created, **kwargs):
    if not created:
        return
    from apps.feed.services import FeedBuilder
    try:
        builder = FeedBuilder(instance.user)
        builder.invalidate()
        if instance.post and instance.post.user:
            builder2 = FeedBuilder(instance.post.user)
            builder2.invalidate()
    except Exception as e:
        logger.error(f"Feed invalidation error (like): {e}")


@receiver(post_save, sender=BattleVote, weak=False)
def invalidate_feed_on_vote(sender, instance, created, **kwargs):
    if not created:
        return
    from apps.feed.services import FeedBuilder
    try:
        builder = FeedBuilder(instance.user)
        builder.invalidate()
    except Exception as e:
        logger.error(f"Feed invalidation error (vote): {e}")


@receiver(post_save, sender=UserActivity, weak=False)
def invalidate_feed_on_activity(sender, instance, created, **kwargs):
    if not created:
        return
    from apps.feed.services import FeedBuilder
    try:
        builder = FeedBuilder(instance.user)
        builder.invalidate()
    except Exception as e:
        logger.error(f"Feed invalidation error (activity): {e}")
