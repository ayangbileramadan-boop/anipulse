from django.utils import timezone
from apps.core.models import Streak
from apps.anime.models import UserActivity
from apps.core.services.gamification import GamificationEngine


def user_streak(request):
    ctx = {}
    if request.user.is_authenticated:
        streak, _ = Streak.objects.get_or_create(user=request.user)
        today = timezone.now().date()
        if streak.last_activity != today:
            streak.check_and_update()
            UserActivity.objects.create(
                user=request.user,
                activity_type='STREAK',
                description=f'{streak.current_streak} day streak!',
            )
        ctx['user_streak'] = streak

        try:
            engine = GamificationEngine()
            profile = engine.get_profile(request.user)
            ctx['game_level'] = profile.level_progress
            ctx['unlocked_badges'] = engine.get_unlocked_badges(request.user)
        except Exception:
            pass
    return ctx
