from django.core.cache import cache
from django.db.models import Q
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
        cache_key = f'feed_v2:{uid}'
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
        cache_key = f'feed_v2:{uid}'
        cache.delete(cache_key)

    def _build_all(self):
        from apps.anime.models import SocialPost, SocialLike
        from apps.core.models import UserFollow

        followed_ids = []
        if self.user and self.user.is_authenticated:
            followed_ids = list(UserFollow.objects.filter(
                follower=self.user
            ).values_list('following_id', flat=True))
            followed_ids.append(self.user.id)

        items = []
        limit = FEED_MAX_ITEMS * 2

        # 1. User posts from followed users (highest priority)
        if followed_ids:
            posts = SocialPost.objects.filter(
                reply_to__isnull=True,
                user_id__in=followed_ids,
                created_at__gte=self.seven_days_ago,
            ).select_related('user', 'anime').order_by('-created_at')[:limit]

            liked_post_ids = set()
            if self.user and self.user.is_authenticated:
                liked_post_ids = set(SocialLike.objects.filter(
                    user=self.user,
                    post_id__in=[p.id for p in posts],
                ).values_list('post_id', flat=True))

            for p in posts:
                items.append(self._serialize_post(p, liked=p.id in liked_post_ids))

        # 2. System/community discussions (always shown, promote the community)
        discussions = SocialPost.objects.filter(
            reply_to__isnull=True,
            post_type__in=['discussion', 'trending', 'seasonal', 'episode_discussion'],
            created_at__gte=self.seven_days_ago,
        ).select_related('user', 'anime').order_by('-created_at')[:limit // 2]

        existing_ids = {item['post_id'] for item in items if 'post_id' in item}
        for p in discussions:
            if p.id not in existing_ids:
                liked = False
                if self.user and self.user.is_authenticated:
                    liked = SocialLike.objects.filter(user=self.user, post_id=p.id).exists()
                items.append(self._serialize_post(p, is_system=True, liked=liked))
                existing_ids.add(p.id)

        # 3. If empty or very sparse, auto-generate trending discussions
        if len(items) < 5:
            auto = self._generate_discussions(exclude_ids=existing_ids)
            items.extend(auto)

        items.sort(key=lambda x: x['timestamp'], reverse=True)
        return items[:FEED_MAX_ITEMS]

    def _serialize_post(self, post, is_system=False, liked=False):
        from django.contrib.contenttypes.models import ContentType
        user_data = self._user_data(post.user)
        if is_system:
            user_data['is_system'] = True
        user_data['liked'] = liked

        ct = ContentType.objects.get_for_model(post)
        comment_count = post.comment_set.count()

        result = {
            'id': f'post_{post.id}',
            'post_id': post.id,
            'type': 'post',
            'subtype': post.post_type,
            'timestamp': post.created_at,
            'user': user_data,
            'content': {
                'title': post.title or '',
                'body': post.body,
                'likes': post.likes,
                'comment_count': comment_count,
                'anime': None,
                'image': post.image or None,
            },
        }
        if post.anime_id:
            result['content']['anime'] = {
                'id': post.anime.anilist_id if hasattr(post, 'anime') and post.anime else None,
                'title': post.anime.display_title if hasattr(post, 'anime') and post.anime else None,
                'image': post.anime.cover_image_medium if hasattr(post, 'anime') and post.anime else None,
            }
        return result

    def _user_data(self, user):
        return {
            'id': user.id,
            'username': user.username,
            'avatar': user.avatar.url if user.avatar and hasattr(user.avatar, 'url') else '',
        }

    def _generate_discussions(self, exclude_ids=None):
        """Auto-generate trending discussion posts from AniList when feed is empty."""
        from apps.anime.models import SocialPost, Anime
        from apps.core.models import UserActivity
        import logging
        logger = logging.getLogger(__name__)

        items = []
        exclude_ids = exclude_ids or set()
        system_user = None
        try:
            from django.contrib.auth import get_user_model
            system_user = get_user_model().objects.filter(is_superuser=True).first()
        except Exception:
            pass
        if not system_user:
            return items

        # Try trending from AniList
        try:
            from apps.anime.services.anilist import AniListClient
            client = AniListClient()
            data = client.get_trending(1, 8)
            trending_list = data.get('data', {}).get('Page', {}).get('media', [])
            for m in trending_list:
                title = m.get('title', {}).get('romaji') or m.get('title', {}).get('english') or 'Unknown'
                anilist_id = m.get('id')
                post, created = SocialPost.objects.get_or_create(
                    post_type='trending',
                    user=system_user,
                    title=f'🔥 Trending: {title}',
                    defaults={
                        'body': f'#{title} is trending! What are your thoughts on this anime?',
                        'anime_id': Anime.objects.filter(anilist_id=anilist_id).first().pk if Anime.objects.filter(anilist_id=anilist_id).exists() else None,
                    }
                )
                if post.id not in exclude_ids:
                    items.append(self._serialize_post(post, is_system=True))
                    exclude_ids.add(post.id)
        except Exception as e:
            logger.warning(f'Failed to generate trending discussions: {e}')

        # Seasonal discussion
        try:
            import datetime
            now = datetime.date.today()
            month = now.month
            season = 'WINTER' if month <= 3 else 'SPRING' if month <= 6 else 'SUMMER' if month <= 9 else 'FALL'
            post, created = SocialPost.objects.get_or_create(
                post_type='seasonal',
                user=system_user,
                title=f'🌸 Best {season} {now.year} Anime?',
                defaults={
                    'body': f'What anime are you watching this {season} {now.year}? Share your favorites and discover new shows!',
                }
            )
            if post.id not in exclude_ids:
                items.append(self._serialize_post(post, is_system=True))
                exclude_ids.add(post.id)
        except Exception as e:
            logger.warning(f'Failed to generate seasonal: {e}')

        # Episode discussion for currently airing popular anime
        try:
            from apps.anime.services.anilist import AniListClient
            client = AniListClient()
            now_airing = client.get_airing(1, 5)
            for m in now_airing.get('data', {}).get('Page', {}).get('media', []):
                title = m.get('title', {}).get('romaji') or m.get('title', {}).get('english') or 'Unknown'
                anilist_id = m.get('id')
                ep = m.get('nextAiringEpisode', {}).get('episode', 'latest')
                post, created = SocialPost.objects.get_or_create(
                    post_type='episode_discussion',
                    user=system_user,
                    title=f'📺 {title} - Episode {ep} Discussion',
                    defaults={
                        'body': f'Discuss the latest episode of {title} here! What did you think?',
                        'anime_id': Anime.objects.filter(anilist_id=anilist_id).first().pk if Anime.objects.filter(anilist_id=anilist_id).exists() else None,
                    }
                )
                if post.id not in exclude_ids:
                    items.append(self._serialize_post(post, is_system=True))
                    exclude_ids.add(post.id)
        except Exception as e:
            logger.warning(f'Failed episode discussions: {e}')

        if not items:
            post, created = SocialPost.objects.get_or_create(
                post_type='discussion',
                user=system_user,
                title='👋 Welcome to AniPulse!',
                defaults={
                    'body': 'Welcome to the community! Start following friends, track your anime, and join discussions. What anime are you watching right now?',
                }
            )
            if post.id not in exclude_ids:
                items.append(self._serialize_post(post, is_system=True))

        return items
