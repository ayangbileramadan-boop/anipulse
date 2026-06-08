from django.core.cache import cache
from django.db.models import Prefetch, Q
from django.utils import timezone
from datetime import timedelta
from itertools import chain

FEED_CACHE_TTL = 300
FEED_PAGE_SIZE = 20
FEED_MAX_ITEMS = 200


class FeedBuilder:
    def __init__(self, user):
        self.user = user
        self.now = timezone.now()
        self.seven_days_ago = self.now - timedelta(days=7)

    def build(self, page=1, page_size=FEED_PAGE_SIZE):
        uid = self.user.id if self.user and self.user.is_authenticated else 0
        cache_key = f'feed:{uid}'
        items = cache.get(cache_key)
        if items is None:
            items = self._build_all()
            cache.set(cache_key, items, FEED_CACHE_TTL)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = items[start:end]
        return {
            'results': page_items,
            'has_next': end < len(items),
            'next_page': page + 1 if end < len(items) else None,
            'total': len(items),
            'page': page,
        }

    def invalidate(self):
        uid = self.user.id if self.user and self.user.is_authenticated else 0
        cache_key = f'feed:{uid}'
        cache.delete(cache_key)

    def _build_all(self):
        from apps.anime.models import SocialPost, UserActivity, BattleVote, SocialLike
        from apps.core.models import UserFollow

        followed_ids = []
        if self.user and self.user.is_authenticated:
            followed_ids = list(UserFollow.objects.filter(
                follower=self.user
            ).values_list('following_id', flat=True))
            followed_ids.append(self.user.id)

        items = []
        limit = FEED_MAX_ITEMS * 2
        liked_post_ids = set()

        if followed_ids:
            posts = SocialPost.objects.filter(
                reply_to__isnull=True,
                user_id__in=followed_ids,
                created_at__gte=self.seven_days_ago,
            ).select_related('user', 'anime').only(
                'id', 'user', 'body', 'anime_id', 'image', 'likes', 'created_at'
            ).order_by('-created_at')[:limit]

            if self.user and self.user.is_authenticated:
                liked_post_ids = set(SocialLike.objects.filter(
                    user=self.user,
                    post_id__in=[p.id for p in posts],
                ).values_list('post_id', flat=True))

            for p in posts:
                items.append(self._serialize_post(p, liked=p.id in liked_post_ids))

            activities = UserActivity.objects.filter(
                user_id__in=followed_ids,
                created_at__gte=self.seven_days_ago,
            ).select_related('user', 'anime').order_by('-created_at')[:limit]

            for a in activities:
                items.append(self._serialize_activity(a))

            votes = BattleVote.objects.filter(
                user_id__in=followed_ids,
                created_at__gte=self.seven_days_ago,
            ).select_related('user', 'battle__anime1', 'battle__anime2').order_by('-created_at')[:limit]

            for v in votes:
                items.append(self._serialize_vote(v))

        system_posts = SocialPost.objects.filter(
            reply_to__isnull=True,
            user__is_superuser=True,
            created_at__gte=self.seven_days_ago,
        ).select_related('user', 'anime').order_by('-created_at')[:limit // 2]

        for p in system_posts:
            items.append(self._serialize_post(p, is_system=True, liked=False))

        if not items:
            return self._generate_fallback()

        items.sort(key=lambda x: x['timestamp'], reverse=True)
        return items[:FEED_MAX_ITEMS]

    def _serialize_post(self, post, is_system=False, liked=False):
        user_data = self._user_data(post.user)
        if is_system:
            user_data['is_system'] = True
        user_data['liked'] = liked
        result = {
            'id': f'post_{post.id}',
            'type': 'system_post' if is_system else 'post',
            'timestamp': post.created_at.isoformat(),
            'user': user_data,
            'content': {
                'body': post.body,
                'likes': post.likes,
                'anime': None,
                'image': post.image or None,
            },
        }
        if post.anime_id:
            result['content']['anime'] = {
                'id': post.anime.anilist_id if hasattr(post, 'anime') and post.anime else None,
                'title': post.anime.display_title if hasattr(post, 'anime') and post.anime else None,
            }
        return result

    def _serialize_activity(self, activity):
        result = {
            'id': f'activity_{activity.id}',
            'type': 'activity',
            'timestamp': activity.created_at.isoformat(),
            'user': self._user_data(activity.user),
            'content': {
                'activity_type': activity.activity_type,
                'description': activity.description,
                'anime': None,
            },
        }
        if activity.anime_id:
            result['content']['anime'] = {
                'id': activity.anime.anilist_id if hasattr(activity, 'anime') and activity.anime else None,
                'title': activity.anime.display_title if hasattr(activity, 'anime') and activity.anime else None,
            }
        return result

    def _serialize_vote(self, vote):
        result = {
            'id': f'vote_{vote.id}',
            'type': 'battle_vote',
            'timestamp': vote.created_at.isoformat(),
            'user': self._user_data(vote.user),
            'content': {
                'choice': vote.choice,
                'anime1': None,
                'anime2': None,
            },
        }
        if hasattr(vote, 'battle') and vote.battle:
            a1 = vote.battle.anime1
            a2 = vote.battle.anime2
            result['content']['anime1'] = {
                'id': a1.anilist_id if a1 else None,
                'title': a1.display_title if a1 else None,
            }
            result['content']['anime2'] = {
                'id': a2.anilist_id if a2 else None,
                'title': a2.display_title if a2 else None,
            }
        return result

    def _user_data(self, user):
        return {
            'id': user.id,
            'username': user.username,
            'avatar': getattr(user, 'avatar', '') or '',
        }

    def _generate_fallback(self):
        items = []

        trending = self._get_trending_fallback()
        items.extend(trending)

        seasonal = self._get_seasonal_fallback()
        items.extend(seasonal)

        most_watched = self._get_most_watched_fallback()
        items.extend(most_watched)

        if not items:
            items.append(self._get_welcome_item())

        items.sort(key=lambda x: x['timestamp'], reverse=True)
        return items[:FEED_MAX_ITEMS]

    def _get_trending_fallback(self):
        items = []
        try:
            from apps.anime.services.anilist import AniListClient
            client = AniListClient()
            trending = client.get_trending(1, 10)
            for i, anime in enumerate(trending.get('data', {}).get('Page', {}).get('media', [])):
                title = anime.get('title', {}).get('romaji', 'Unknown')
                cover = anime.get('coverImage', {}).get('large', '')
                items.append({
                    'id': f'trending_{anime.get("id", i)}',
                    'type': 'system_trending',
                    'timestamp': self.now.isoformat(),
                    'user': {'id': 0, 'username': 'AniPulse', 'avatar': '', 'is_system': True},
                    'content': {
                        'title': title,
                        'image': cover,
                        'subtitle': f'#{i+1} Trending',
                        'anime_id': anime.get('id'),
                        'action': 'trending',
                    },
                })
        except Exception:
            pass
        return items

    def _get_seasonal_fallback(self):
        items = []
        try:
            from apps.anime.services.anilist import AniListClient
            import datetime
            now = datetime.date.today()
            month = now.month
            if month <= 3:
                season = 'WINTER'
            elif month <= 6:
                season = 'SPRING'
            elif month <= 9:
                season = 'SUMMER'
            else:
                season = 'FALL'
            client = AniListClient()
            seasonal = client.get_popular_this_season(season, now.year, 1, 10)
            for i, anime in enumerate(seasonal.get('data', {}).get('Page', {}).get('media', [])):
                title = anime.get('title', {}).get('romaji', 'Unknown')
                cover = anime.get('coverImage', {}).get('large', '')
                items.append({
                    'id': f'seasonal_{anime.get("id", i)}',
                    'type': 'system_seasonal',
                    'timestamp': self.now.isoformat(),
                    'user': {'id': 0, 'username': 'AniPulse', 'avatar': '', 'is_system': True},
                    'content': {
                        'title': title,
                        'image': cover,
                        'subtitle': f'Top {season} {now.year}',
                        'anime_id': anime.get('id'),
                        'action': 'seasonal',
                    },
                })
        except Exception:
            pass
        return items

    def _get_most_watched_fallback(self):
        items = []
        try:
            from apps.watchlist.models import WatchlistEntry
            today_start = self.now.replace(hour=0, minute=0, second=0, microsecond=0)
            entries = WatchlistEntry.objects.filter(
                updated_at__gte=today_start,
                progress__gt=0,
            ).select_related('anime').order_by('-progress')[:10]
            for i, e in enumerate(entries):
                a = e.anime
                if not a:
                    continue
                items.append({
                    'id': f'watched_{a.anilist_id}',
                    'type': 'system_most_watched',
                    'timestamp': self.now.isoformat(),
                    'user': {'id': 0, 'username': 'AniPulse', 'avatar': '', 'is_system': True},
                    'content': {
                        'title': a.display_title,
                        'image': a.cover_image_medium or '',
                        'subtitle': f'{e.progress} episodes watched today',
                        'anime_id': a.anilist_id,
                        'action': 'most_watched',
                    },
                })
        except Exception:
            pass
        return items

    def _get_welcome_item(self):
        return {
            'id': 'welcome_1',
            'type': 'system_welcome',
            'timestamp': self.now.isoformat(),
            'user': {'id': 0, 'username': 'AniPulse', 'avatar': '', 'is_system': True},
            'content': {
                'title': 'Welcome to AniPulse!',
                'body': 'Start following friends, track anime, and vote in battles to personalize your feed.',
                'action': 'welcome',
            },
        }
