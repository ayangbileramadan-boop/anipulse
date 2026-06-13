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
        from apps.anime.models import SocialPost, SocialLike, Bookmark
        from apps.core.models import UserFollow

        followed_ids = []
        uid = self.user.id if self.user and self.user.is_authenticated else 0
        if uid:
            followed_ids = list(UserFollow.objects.filter(
                follower=self.user
            ).values_list('following_id', flat=True))
            followed_ids.append(uid)

        items = []
        limit = FEED_MAX_ITEMS * 2
        all_types = ['post', 'discussion', 'trending', 'seasonal', 'episode_discussion',
                     'poll', 'qotd', 'hot_take', 'recommendation',
                     'share_battle', 'share_tierlist', 'share_review']

        # Base queryset — all non-reply posts from last 7 days
        base_qs = SocialPost.objects.filter(
            reply_to__isnull=True,
            post_type__in=all_types,
            created_at__gte=self.seven_days_ago,
        ).select_related('user', 'anime').order_by('-created_at')

        # 1. Priority: posts from followed users
        if followed_ids:
            followed_posts = base_qs.filter(user_id__in=followed_ids)
            all_posts = list(followed_posts[:limit])
        else:
            all_posts = []

        # 2. Fill with community posts (prominent types) if we don't have enough
        if len(all_posts) < limit:
            community_types = ['discussion', 'episode_discussion', 'trending', 'seasonal',
                               'qotd', 'hot_take', 'recommendation', 'poll']
            extra = base_qs.filter(post_type__in=community_types)
            if followed_ids:
                extra = extra.exclude(user_id__in=followed_ids)
            existing = {p.id for p in all_posts}
            for p in extra:
                if p.id not in existing:
                    all_posts.append(p)
                    existing.add(p.id)
                    if len(all_posts) >= limit:
                        break

        # 3. Bulk fetch like, bookmark status
        liked_ids = set()
        bm_ids = set()
        pids = [p.id for p in all_posts]
        if uid:
            liked_ids = set(SocialLike.objects.filter(user=self.user, post_id__in=pids).values_list('post_id', flat=True))
            bm_ids = set(Bookmark.objects.filter(user=self.user, post_id__in=pids).values_list('post_id', flat=True))

        for p in all_posts:
            items.append(self._serialize_post(
                p,
                liked=p.id in liked_ids,
                bookmarked=p.id in bm_ids,
            ))

        # 4. Auto-generate community content if sparse
        existing_ids = {item['post_id'] for item in items}
        if len(items) < 10:
            auto = self._generate_discussions(exclude_ids=existing_ids)
            items.extend(auto)

        items.sort(key=lambda x: x['timestamp'], reverse=True)
        return items[:FEED_MAX_ITEMS]

    def _serialize_post(self, post, is_system=False, liked=False, bookmarked=False):
        from django.contrib.contenttypes.models import ContentType
        user_data = self._user_data(post.user)
        if is_system:
            user_data['is_system'] = True
        user_data['liked'] = liked

        comment_count = post.comments.count()
        bookmark_count = post.bookmarks.count() if hasattr(post, 'bookmarks') else 0

        result = {
            'id': f'post_{post.id}',
            'post_id': post.id,
            'type': 'post',
            'subtype': post.post_type,
            'timestamp': post.created_at,
            'user': user_data,
            'bookmarked': bookmarked,
            'content': {
                'title': post.title or '',
                'body': post.body,
                'likes': post.likes,
                'comment_count': comment_count,
                'bookmark_count': bookmark_count,
                'anime': None,
                'image': post.image or None,
                'poll': None,
            },
        }

        # Rich anime card
        if post.anime_id and post.anime:
            a = post.anime
            result['content']['anime'] = {
                'id': a.anilist_id,
                'title': a.display_title,
                'image': a.cover_image_medium,
                'score': a.average_score,
                'episodes': a.episodes,
                'popularity': a.popularity,
                'studio': ', '.join(s.name for s in a.studios.all()[:2]) if hasattr(a, 'studios') and a.studios.exists() else None,
                'format': a.format,
                'year': a.season_year,
            }

        # Poll data
        if post.post_type == 'poll' and hasattr(post, 'poll') and post.poll:
            poll = post.poll
            options = [{
                'id': o.id, 'text': o.text, 'votes': o.vote_count,
                'pct': o.percentage(poll.total_votes),
            } for o in poll.options.all()]
            result['content']['poll'] = {
                'question': poll.question,
                'total_votes': poll.total_votes,
                'options': options,
            }

        # Share data
        if post.is_share and post.shared_obj:
            shared = post.shared_obj
            result['content']['shared'] = {
                'type': post.post_type.replace('share_', ''),
                'title': str(shared)[:100],
                'url': getattr(shared, 'get_absolute_url', lambda: '#')(),
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

        # Question of the Day
        try:
            qotd_questions = [
                'Which anime has the best soundtrack?',
                'What anime made you cry the most?',
                'Which anime character do you relate to most?',
                'What is your all-time favorite anime?',
                'Which anime has the best animation?',
                'What anime would you recommend to a beginner?',
                'Which anime ending hit you the hardest?',
                'What anime world would you want to live in?',
            ]
            import random
            from datetime import date
            qotd_q = qotd_questions[hash(str(date.today())) % len(qotd_questions)]
            post, created = SocialPost.objects.get_or_create(
                post_type='qotd',
                user=system_user,
                title=f'💬 Question of the Day',
                defaults={'body': qotd_q}
            )
            if post.id not in exclude_ids:
                items.append(self._serialize_post(post, is_system=True))
                exclude_ids.add(post.id)
        except Exception:
            pass

        # Hot Take
        try:
            hot_takes = [
                'Is Solo Leveling overrated?',
                'One Piece is too long — change my mind.',
                'Dubs are better than subs.',
                '10-episode anime are the perfect length.',
                'Classic anime are better than modern ones.',
                'Romance anime need more actual relationships.',
            ]
            hot = hot_takes[hash(str(date.today()) + str(random.randint(0, 99))) % len(hot_takes)]
            post, created = SocialPost.objects.get_or_create(
                post_type='hot_take',
                user=system_user,
                title=f'🔥 Hot Take',
                defaults={'body': hot}
            )
            if post.id not in exclude_ids:
                items.append(self._serialize_post(post, is_system=True))
                exclude_ids.add(post.id)
        except Exception:
            pass

        # Recommendation Thread
        try:
            recs = [
                'What to watch after finishing Attack on Titan?',
                'Suggest some hidden gem anime from the 90s.',
                'Best anime for fans of great fight choreography?',
                'Need something like Frieren — slow, emotional, beautiful.',
            ]
            rec = recs[hash(str(date.today()) + str(random.randint(0, 999))) % len(recs)]
            post, created = SocialPost.objects.get_or_create(
                post_type='recommendation',
                user=system_user,
                title=f'📚 Recommendation Thread',
                defaults={'body': rec}
            )
            if post.id not in exclude_ids:
                items.append(self._serialize_post(post, is_system=True))
                exclude_ids.add(post.id)
        except Exception:
            pass

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
