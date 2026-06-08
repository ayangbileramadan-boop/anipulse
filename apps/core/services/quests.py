"""
Daily/weekly quest generation and progress tracking.
"""

import random
from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils.timezone import now

from apps.core.models import UserProfile, UserQuest
from apps.core.services.gamification import XP_RATES

DAILY_QUESTS = [
    {
        'quest_id': 'daily_watch_1',
        'title': 'Watch an Episode',
        'description': 'Watch 1 episode of any anime',
        'target': 1,
        'xp_reward': XP_RATES['complete_episode'] * 2,
    },
    {
        'quest_id': 'daily_watch_3',
        'title': 'Binge Session',
        'description': 'Watch 3 episodes of any anime',
        'target': 3,
        'xp_reward': XP_RATES['complete_episode'] * 5,
    },
    {
        'quest_id': 'daily_login',
        'title': 'Daily Login',
        'description': 'Log in and check your streak',
        'target': 1,
        'xp_reward': XP_RATES['daily_login'] * 2,
    },
    {
        'quest_id': 'daily_episode',
        'title': 'Episode Watcher',
        'description': 'Watch 1 episode',
        'target': 1,
        'xp_reward': XP_RATES['complete_episode'] * 2,
    },
    {
        'quest_id': 'daily_review',
        'title': 'Share Your Thoughts',
        'description': 'Write a review for an anime',
        'target': 1,
        'xp_reward': XP_RATES['add_review'] * 2,
    },
    {
        'quest_id': 'daily_add_3',
        'title': 'Add to Watchlist',
        'description': 'Add 3 anime to your watchlist',
        'target': 3,
        'xp_reward': XP_RATES['add_to_watchlist'] * 3,
    },
]

WEEKLY_QUESTS = [
    {
        'quest_id': 'weekly_complete_3',
        'title': 'Completionist',
        'description': 'Complete 3 anime',
        'target': 3,
        'xp_reward': XP_RATES['complete_anime'] * 4,
    },
    {
        'quest_id': 'weekly_watch_20',
        'title': 'Heavy Watcher',
        'description': 'Watch 20 episodes total',
        'target': 20,
        'xp_reward': XP_RATES['complete_episode'] * 10,
    },
    {
        'quest_id': 'weekly_reviews_3',
        'title': 'Prolific Critic',
        'description': 'Write 3 reviews',
        'target': 3,
        'xp_reward': XP_RATES['add_review'] * 5,
    },
    {
        'quest_id': 'weekly_add_10',
        'title': 'Collector',
        'description': 'Add 10 anime to your watchlist',
        'target': 10,
        'xp_reward': XP_RATES['add_to_watchlist'] * 5,
    },
    {
        'quest_id': 'weekly_battles_3',
        'title': 'Competitor',
        'description': 'Vote in 3 battles',
        'target': 3,
        'xp_reward': XP_RATES['vote_battle'] * 5,
    },
]


def generate_daily_quests(user, count=2):
    """Assign `count` random daily quests to a user."""
    chosen = random.sample(DAILY_QUESTS, min(count, len(DAILY_QUESTS)))
    expires = now() + timedelta(days=1)
    created = []
    for q in chosen:
        _, c = UserQuest.objects.get_or_create(
            user=user,
            quest_id=q['quest_id'],
            expires_at__gt=now(),
            defaults={
                'title': q['title'],
                'description': q['description'],
                'target': q['target'],
                'xp_reward': q['xp_reward'],
                'expires_at': expires,
            },
        )
        if c:
            created.append(q)
    return created


def generate_weekly_quests(user, count=1):
    """Assign `count` random weekly quests to a user."""
    chosen = random.sample(WEEKLY_QUESTS, min(count, len(WEEKLY_QUESTS)))
    expires = now() + timedelta(days=7)
    created = []
    for q in chosen:
        _, c = UserQuest.objects.get_or_create(
            user=user,
            quest_id=q['quest_id'],
            expires_at__gt=now(),
            defaults={
                'title': q['title'],
                'description': q['description'],
                'target': q['target'],
                'xp_reward': q['xp_reward'],
                'expires_at': expires,
            },
        )
        if c:
            created.append(q)
    return created


@transaction.atomic
def progress_quest(user, quest_id_prefix, amount=1):
    """Increment progress for all matching active quests."""
    qs = UserQuest.objects.filter(
        user=user,
        quest_id__startswith=quest_id_prefix,
        completed=False,
        expires_at__gt=now(),
    )
    for quest in qs:
        quest.refresh_from_db()
        new_progress = min(quest.progress + amount, quest.target)
        UserQuest.objects.filter(id=quest.id).update(progress=new_progress)
        quest.refresh_from_db()
        if quest.progress >= quest.target:
            quest.completed = True
            quest.completed_at = now()
            profile, _ = UserProfile.objects.get_or_create(user=user)
            UserProfile.objects.filter(user=user).update(total_xp=F('total_xp') + quest.xp_reward)
            profile.refresh_from_db()
        quest.save(update_fields=['progress', 'completed', 'completed_at'])
