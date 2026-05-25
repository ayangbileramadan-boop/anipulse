"""
Gamification engine: XP, levels, badges, quests, streaks.
"""

import logging

from django.db.models import Sum

from apps.core.models import UserProfile, UserBadge, Streak, Notification
from apps.watchlist.models import WatchlistEntry

logger = logging.getLogger(__name__)

# ─── XP Configuration ─────────────────────────────

XP_RATES = {
    'add_to_watchlist': 10,
    'complete_episode': 5,
    'complete_anime': 50,
    'add_review': 30,
    'like_review': 2,
    'create_post': 15,
    'create_battle': 20,
    'vote_battle': 5,
    'daily_login': 25,
    'comment': 10,
    'update_profile': 15,
    'share_activity': 10,
}

LEVEL_TABLE = [
    (1, 0),
    (2, 100),
    (3, 250),
    (4, 500),
    (5, 800),
    (6, 1200),
    (7, 1700),
    (8, 2300),
    (9, 3000),
    (10, 4000),
    (11, 5200),
    (12, 6600),
    (13, 8200),
    (14, 10000),
    (15, 12000),
    (16, 14500),
    (17, 17500),
    (18, 21000),
    (19, 25000),
    (20, 30000),
    (25, 50000),
    (30, 80000),
    (35, 120000),
    (40, 180000),
    (45, 250000),
    (50, 400000),
]


def xp_for_level(level):
    for lvl, xp in reversed(LEVEL_TABLE):
        if level >= lvl:
            return xp
    return 0


def level_for_xp(xp):
    for lvl, req in reversed(LEVEL_TABLE):
        if xp >= req:
            return lvl, xp - req
    return 1, xp


# ─── Badges ───────────────────────────────────────

BADGE_DEFS = {
    'first_anime': {'name': 'First Steps', 'desc': 'Add your first anime to the watchlist', 'icon': '\uD83C\uDF1F'},
    'ten_watchlist': {'name': 'Getting Started', 'desc': 'Add 10 anime to your watchlist', 'icon': '\uD83D\uDCDD'},
    'fifty_watchlist': {'name': 'Otaku in Training', 'desc': 'Add 50 anime to your watchlist', 'icon': '\uD83C\uDF93'},
    'anime_complete_10': {'name': 'Completionist I', 'desc': 'Complete 10 anime', 'icon': '\u2705'},
    'anime_complete_50': {'name': 'Completionist II', 'desc': 'Complete 50 anime', 'icon': '\uD83C\uDFC6'},
    'anime_complete_100': {'name': 'Completionist III', 'desc': 'Complete 100 anime', 'icon': '\uD83D\uDC51'},
    'streak_7': {'name': 'Week Warrior', 'desc': '7-day login streak', 'icon': '\uD83D\uDD25'},
    'streak_30': {'name': 'Monthly Devotion', 'desc': '30-day login streak', 'icon': '\uD83C\uDF18'},
    'streak_100': {'name': 'Century', 'desc': '100-day login streak', 'icon': '\uD83D\uDCAA'},
    'review_10': {'name': 'Critic', 'desc': 'Write 10 reviews', 'icon': '\u270D\uFE0F'},
    'battle_10': {'name': 'Competitor', 'desc': 'Participate in 10 battles', 'icon': '\u2694\uFE0F'},
    'social_butterfly': {'name': 'Social Butterfly', 'desc': 'Follow 10 users', 'icon': '\uD83E\uDD8B'},
    'watcher_100': {'name': '100 Episodes', 'desc': 'Watch 100 episodes total', 'icon': '\uD83D\uDC40'},
    'watcher_1000': {'name': 'Marathoner', 'desc': 'Watch 1000 episodes total', 'icon': '\uD83C\uDFC3'},
    'watcher_10000': {'name': 'Legendary', 'desc': 'Watch 10000 episodes total', 'icon': '\uD83C\uDFC6'},
    'early_adopter': {'name': 'Early Adopter', 'desc': 'Joined in the first month', 'icon': '\uD83D\uDC96'},
    'curator': {'name': 'Curator', 'desc': 'Create 5 tier lists', 'icon': '\uD83D\uDCCA'},
    'reviewer_50': {'name': 'Prolific Critic', 'desc': 'Write 50 reviews', 'icon': '\uD83C\uDF1F'},
}


class GamificationEngine:
    """
    Handles XP awards, level-ups, badge checks, and quest tracking.
    All operations are idempotent and safe to call multiple times.
    """

    def award_xp(self, user, action):
        """Award XP for an action and check for level-ups."""
        amount = XP_RATES.get(action, 0)
        if not amount or not user:
            return

        profile, _ = UserProfile.objects.get_or_create(user=user)
        if profile.total_xp is None:
            profile.total_xp = 0
        old_level = level_for_xp(profile.total_xp)[0]
        profile.total_xp += amount
        profile.save(update_fields=['total_xp'])

        new_level = level_for_xp(profile.total_xp)[0]
        if new_level > old_level:
            try:
                self._on_level_up(user, new_level, profile)
            except Exception as e:
                logger.error(f"Level-up notif failed for {user.id}: {e}")

        try:
            self.check_badges(user)
        except Exception as e:
            logger.error(f"Badge check failed for {user.id}: {e}")

    def check_badges(self, user):
        """Evaluate and award any newly earned badges."""
        stats = self._user_stats(user)
        earned = set(UserBadge.objects.filter(user=user).values_list('badge_id', flat=True))

        to_award = []
        for badge_id, defn in BADGE_DEFS.items():
            if badge_id in earned:
                continue
            if self._check_badge_condition(badge_id, user, stats):
                to_award.append(UserBadge(user=user, badge_id=badge_id))

        if to_award:
            UserBadge.objects.bulk_create(to_award, ignore_conflicts=True)
            for badge in to_award:
                self._on_badge_earned(user, badge.badge_id)

        return to_award

    def get_profile(self, user):
        """Get or create gamification profile."""
        profile, created = UserProfile.objects.get_or_create(user=user)
        return profile

    def get_unlocked_badges(self, user):
        """Return all badge definitions the user has earned."""
        earned = set(UserBadge.objects.filter(user=user).values_list('badge_id', flat=True))
        return {bid: BADGE_DEFS[bid] for bid in earned if bid in BADGE_DEFS}

    def get_level_progress(self, user):
        """Return current level, XP, and progress to next level."""
        profile = self.get_profile(user)
        xp = profile.total_xp or 0
        level, remainder = level_for_xp(xp)
        next_xp = xp_for_level(level + 1) - xp_for_level(level) if level < 50 else 1
        progress = min(remainder / max(next_xp, 1) * 100, 100) if next_xp > 0 else 100
        return {
            'level': level,
            'xp': xp,
            'xp_to_next': max(next_xp - remainder, 0),
            'progress_pct': round(progress, 1),
        }

    # ─── Private helpers ──────────────────────────

    def _on_level_up(self, user, level, profile):
        try:
            Notification.objects.create(
                user=user,
                title=f'Level {level}!',
                message=f'You reached level {level}. Keep it up!',
                url='/profile/',
            )
        except Exception:
            pass

    def _on_badge_earned(self, user, badge_id):
        defn = BADGE_DEFS.get(badge_id, {})
        try:
            Notification.objects.create(
                user=user,
                title=f'Badge Unlocked: {defn.get("name", badge_id)}',
                message=defn.get('desc', ''),
                url='/profile/',
            )
        except Exception:
            pass

    def _user_stats(self, user):
        entries = WatchlistEntry.objects.filter(user=user)
        return {
            'total_entries': entries.count(),
            'completed': entries.filter(status='COMPLETED').count(),
            'total_episodes': entries.aggregate(s=Sum('episodes_watched'))['s'] or 0,
            'reviews': user.reviews.count(),
            'battles': user.battle_set.count() + user.battlevote_set.count(),
            'followers': user.followers.count(),
            'following': user.following.count(),
            'tier_lists': user.tier_lists.count(),
            'streak_days': self._get_streak_days(user),
        }

    def _check_badge_condition(self, badge_id, user, stats):
        checks = {
            'first_anime': lambda s: s['total_entries'] >= 1,
            'ten_watchlist': lambda s: s['total_entries'] >= 10,
            'fifty_watchlist': lambda s: s['total_entries'] >= 50,
            'anime_complete_10': lambda s: s['completed'] >= 10,
            'anime_complete_50': lambda s: s['completed'] >= 50,
            'anime_complete_100': lambda s: s['completed'] >= 100,
            'streak_7': lambda s: s['streak_days'] >= 7,
            'streak_30': lambda s: s['streak_days'] >= 30,
            'streak_100': lambda s: s['streak_days'] >= 100,
            'review_10': lambda s: s['reviews'] >= 10,
            'battle_10': lambda s: s['battles'] >= 10,
            'social_butterfly': lambda s: s['following'] >= 10,
            'watcher_100': lambda s: s['total_episodes'] >= 100,
            'watcher_1000': lambda s: s['total_episodes'] >= 1000,
            'watcher_10000': lambda s: s['total_episodes'] >= 10000,
            'curator': lambda s: s['tier_lists'] >= 5,
            'reviewer_50': lambda s: s['reviews'] >= 50,
        }
        check = checks.get(badge_id)
        return check(stats) if check else False

    def _get_streak_days(self, user):
        try:
            streak = Streak.objects.get(user=user)
            return streak.current_streak
        except Streak.DoesNotExist:
            return 0



