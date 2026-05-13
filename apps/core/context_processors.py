from django.utils import timezone
from apps.anime.models import Streak, UserActivity


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
    return ctx
