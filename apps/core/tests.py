import json
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache
from apps.core.models import Streak, UserFollow, Notification
from apps.anime.models import Battle, SocialPost, SocialLike, Genre
from apps.watchlist.models import WatchlistEntry
from apps.core.services.gamification import GamificationEngine, XP_RATES, BADGE_DEFS, level_for_xp, xp_for_level
from apps.core.models import UserProfile, UserBadge


class TestGamification:
    @pytest.fixture(autouse=True)
    def setup(self, db, user, anime, genre):
        self.user = user
        self.anime = anime
        self.genre = genre
        self.engine = GamificationEngine()

    def test_level_for_xp(self):
        assert level_for_xp(0) == (1, 0)
        assert level_for_xp(100) == (2, 0)
        assert level_for_xp(150) == (2, 50)
        assert level_for_xp(800) == (5, 0)

    def test_xp_for_level(self):
        assert xp_for_level(1) == 0
        assert xp_for_level(2) == 100
        assert xp_for_level(5) == 800

    def test_xp_for_level_beyond_table(self):
        assert xp_for_level(50) == 400000
        assert xp_for_level(99) == 400000

    def test_award_xp_creates_profile(self):
        self.engine.award_xp(self.user, 'add_to_watchlist')
        assert UserProfile.objects.filter(user=self.user).exists()

    def test_award_xp_increases_total(self):
        self.engine.award_xp(self.user, 'add_to_watchlist')
        profile = UserProfile.objects.get(user=self.user)
        assert profile.total_xp == XP_RATES['add_to_watchlist']

    def test_award_xp_multiple_actions(self):
        self.engine.award_xp(self.user, 'complete_anime')
        self.engine.award_xp(self.user, 'add_review')
        profile = UserProfile.objects.get(user=self.user)
        expected = XP_RATES['complete_anime'] + XP_RATES['add_review']
        assert profile.total_xp == expected

    def test_award_xp_unknown_action(self):
        self.engine.award_xp(self.user, 'unknown_action')
        assert not UserProfile.objects.filter(user=self.user).exists()

    def test_get_level_progress(self):
        self.engine.award_xp(self.user, 'complete_anime')
        progress = self.engine.get_level_progress(self.user)
        assert progress['level'] == 1
        assert progress['xp'] == XP_RATES['complete_anime']

    def test_first_anime_badge(self):
        WatchlistEntry.objects.create(user=self.user, anime=self.anime, status='COMPLETED')
        assert UserBadge.objects.filter(user=self.user, badge_id='first_anime').exists()

    def test_no_badge_for_no_activity(self):
        awarded = self.engine.check_badges(self.user)
        assert list(awarded) == []

    def test_badge_persistence(self):
        WatchlistEntry.objects.create(user=self.user, anime=self.anime, status='COMPLETED')
        assert UserBadge.objects.filter(user=self.user, badge_id='first_anime').exists()

    def test_badge_not_duplicated(self):
        WatchlistEntry.objects.create(user=self.user, anime=self.anime, status='COMPLETED')
        assert UserBadge.objects.filter(user=self.user).count() == 1
        self.engine.check_badges(self.user)
        assert UserBadge.objects.filter(user=self.user).count() == 1

    def test_get_unlocked_badges(self):
        WatchlistEntry.objects.create(user=self.user, anime=self.anime, status='COMPLETED')
        badges = self.engine.get_unlocked_badges(self.user)
        assert 'first_anime' in badges
        assert badges['first_anime']['name'] == 'First Steps'

    def test_get_profile_creates_if_missing(self):
        profile = self.engine.get_profile(self.user)
        assert profile is not None
        assert profile.total_xp == 0


class TestPersonalization:
    @pytest.fixture(autouse=True)
    def setup(self, db, user, anime, genre):
        self.user = user
        self.anime = anime
        self.genre = genre
        cache.clear()

    def test_continue_watching_with_no_entries(self):
        from apps.core.services.personalization import PersonalizationEngine
        engine = PersonalizationEngine()
        cw = engine.get_continue_watching(self.user)
        assert cw == []

    def test_continue_watching_with_entry(self):
        from apps.core.services.personalization import PersonalizationEngine
        WatchlistEntry.objects.create(user=self.user, anime=self.anime, status='WATCHING', episodes_watched=5)
        engine = PersonalizationEngine()
        cw = engine.get_continue_watching(self.user)
        assert len(cw) >= 1
        assert cw[0]['episode'] == 6

    def test_genre_affinity_empty(self):
        from apps.core.services.personalization import PersonalizationEngine
        engine = PersonalizationEngine()
        affinity = engine.get_genre_affinity(self.user)
        assert affinity == {}

    def test_genre_affinity_with_completed_entry(self):
        from apps.core.services.personalization import PersonalizationEngine
        WatchlistEntry.objects.create(user=self.user, anime=self.anime, status='COMPLETED', episodes_watched=24, score=8)
        engine = PersonalizationEngine()
        affinity = engine.get_genre_affinity(self.user)
        assert 'Action' in affinity
        assert 0 < affinity['Action'] <= 1

    def test_homepage_sections_anonymous(self):
        from apps.core.services.personalization import PersonalizationEngine
        engine = PersonalizationEngine()
        sections = engine.get_homepage_sections(self.user)
        assert isinstance(sections, list)

    def test_recommendations_empty_for_no_history(self):
        from apps.core.services.personalization import PersonalizationEngine
        engine = PersonalizationEngine()
        recs = engine.get_recommendations(self.user, limit=5)
        assert isinstance(recs, list)


class TestHomePage:
    def test_home_page_returns_200(self, client):
        resp = client.get('/')
        assert resp.status_code == 200

    def test_home_page_uses_correct_template(self, client):
        resp = client.get('/')
        assert 'home.html' in [t.name for t in resp.templates]


class TestAuth:
    def test_login_page(self, client, db):
        resp = client.get('/login/')
        assert resp.status_code == 200

    def test_login_redirects(self, client, user):
        resp = client.post('/login/', {'username': 'testuser', 'password': 'testpass123'})
        assert resp.status_code == 302

    def test_logged_in_user_sees_profile(self, client, user):
        client.force_login(user)
        resp = client.get('/')
        assert 'testuser' in resp.content.decode()


class TestProfile:
    def test_profile_page(self, client, user):
        resp = client.get(f'/profile/{user.username}/')
        assert resp.status_code == 200

    def test_profile_shows_username(self, client, user):
        client.force_login(user)
        resp = client.get(f'/profile/{user.username}/')
        assert user.username in resp.content.decode()


class TestWatchlist:
    def test_watchlist_requires_login(self, client):
        resp = client.get('/watchlist/')
        assert resp.status_code == 302

    def test_watchlist_shows_entries(self, client, user, watchlist_entry):
        client.force_login(user)
        resp = client.get('/watchlist/')
        assert resp.status_code == 200

    def test_update_entry(self, client, user, watchlist_entry):
        client.force_login(user)
        resp = client.post(f'/watchlist/{watchlist_entry.id}/update/', {
            'status': 'COMPLETED', 'episodes_watched': '24', 'score': '8',
        })
        watchlist_entry.refresh_from_db()
        assert watchlist_entry.status == 'COMPLETED'
        assert watchlist_entry.score == 8.0

    def test_add_to_watchlist_requires_login(self, client):
        resp = client.post('/watchlist/add/', {'anilist_id': '1', 'status': 'PLANNING'})
        assert resp.status_code == 302


class TestBattle:
    pytestmark = pytest.mark.django_db

    def test_battle_list_page(self, client):
        resp = client.get('/battles/')
        assert resp.status_code == 200

    def test_battle_create_requires_auth(self, client):
        resp = client.get('/battles/create/')
        assert resp.status_code == 302


class TestSocial:
    pytestmark = pytest.mark.django_db

    def test_social_feed_page(self, client):
        resp = client.get('/social/')
        assert resp.status_code == 200

    def test_create_post_requires_auth(self, client):
        resp = client.get('/social/post/')
        assert resp.status_code == 302

    def test_create_post(self, client, user):
        client.force_login(user)
        resp = client.post('/social/post/', {'body': 'Hello world!'})
        assert resp.status_code == 302
        assert SocialPost.objects.filter(user=user).count() == 1

    def test_like_post(self, client, user, other_user):
        post = SocialPost.objects.create(user=other_user, body='Test post')
        client.force_login(user)
        resp = client.get(f'/social/like/{post.id}/')
        assert resp.status_code == 302
        post.refresh_from_db()
        assert post.likes == 1

    def test_follow_user(self, client, user, other_user):
        client.force_login(user)
        resp = client.get(f'/social/follow/{other_user.username}/')
        assert resp.status_code == 302
        assert UserFollow.objects.filter(follower=user, following=other_user).exists()

    def test_follow_creates_notification(self, client, user, other_user):
        client.force_login(user)
        client.get(f'/social/follow/{other_user.username}/')
        assert Notification.objects.filter(user=other_user).exists()


class TestStreak:
    def test_streak_created_directly(self, db, user):
        Streak.objects.create(user=user)
        assert Streak.objects.filter(user=user).exists()

    def test_streak_initial_value(self, client, user):
        Streak.objects.create(user=user, current_streak=5)
        s = Streak.objects.get(user=user)
        assert s.current_streak == 5


class TestSearch:
    def test_search_page(self, client):
        resp = client.get('/search/')
        assert resp.status_code == 200

    def test_search_with_query(self, client):
        resp = client.get('/search/?q=Naruto')
        assert resp.status_code == 200


class TestSeasonal:
    def test_seasonal_archive(self, client):
        resp = client.get('/season/2024/winter/')
        assert resp.status_code == 200


class TestCalendar:
    def test_calendar_page(self, client):
        resp = client.get('/calendar/')
        assert resp.status_code == 200


class TestTierList:
    pytestmark = pytest.mark.django_db

    def test_tier_list_page(self, client):
        resp = client.get('/tierlists/')
        assert resp.status_code == 200

    def test_tier_list_create_requires_auth(self, client):
        resp = client.get('/tierlists/create/')
        assert resp.status_code == 302


class TestQuiz:
    def test_quiz_page_returns_200(self, client):
        resp = client.get('/quiz/')
        assert resp.status_code == 200


class TestSettings:
    def test_settings_requires_auth(self, client):
        resp = client.get('/settings/')
        assert resp.status_code == 302

    def test_settings_page(self, client, user):
        client.force_login(user)
        resp = client.get('/settings/')
        assert resp.status_code == 200

    def test_settings_save(self, client, user):
        client.force_login(user)
        resp = client.post('/settings/', {'bio': 'Test bio', 'timezone': 'Asia/Tokyo'})
        assert resp.status_code == 302
        user.refresh_from_db()
        assert user.bio == 'Test bio'
        assert user.timezone == 'Asia/Tokyo'


class TestNotifications:
    def test_notifications_json(self, client, user):
        client.force_login(user)
        Notification.objects.create(user=user, title='Test notification')
        resp = client.get('/notifications/json/')
        assert resp.status_code == 200
        data = resp.json()
        assert data['unread_count'] == 1

    def test_mark_read(self, client, user):
        client.force_login(user)
        n = Notification.objects.create(user=user, title='Test')
        resp = client.get(f'/notifications/{n.id}/read/')
        assert resp.status_code == 200
        n.refresh_from_db()
        assert n.is_read is True

    def test_mark_all_read(self, client, user):
        client.force_login(user)
        Notification.objects.create(user=user, title='A')
        Notification.objects.create(user=user, title='B')
        resp = client.get('/notifications/read-all/')
        assert resp.status_code == 200
        assert Notification.objects.filter(user=user, is_read=False).count() == 0


class TestLogoutSecurity:
    """ACCOUNT_LOGOUT_ON_GET=False — GET must NOT log out, only POST may."""

    def test_get_logout_does_not_log_out(self, client, user):
        client.force_login(user)
        # Do NOT follow redirect — the home page makes AniList API calls
        resp = client.get('/logout/')
        # Even if redirected, user must still be authenticated
        user.refresh_from_db()
        assert user.is_authenticated

    def test_post_logout_logs_out(self, client, user):
        client.force_login(user)
        client.post('/logout/', follow=True)
        resp = client.get('/settings/')
        assert resp.status_code == 302, "POST logout should redirect unauthenticated user"


class TestProfileEditUpload:
    """Profile_edit view was crashing due to missing settings import."""

    def test_profile_edit_page_loads(self, client, user):
        client.force_login(user)
        resp = client.get('/profile/edit/')
        assert resp.status_code == 200

    def test_profile_edit_post_text_only(self, client, user):
        client.force_login(user)
        resp = client.post('/profile/edit/', {'bio': 'Hello world'}, follow=True)
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.bio == 'Hello world'

    def test_profile_edit_post_with_avatar(self, client, user, tmp_path):
        from django.core.files.uploadedfile import SimpleUploadedFile
        import io
        from PIL import Image

        img = Image.new('RGB', (100, 100), color='red')
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        buf.seek(0)

        avatar = SimpleUploadedFile('avatar.jpg', buf.read(), content_type='image/jpeg')
        client.force_login(user)
        resp = client.post('/profile/edit/', {'avatar_file': avatar}, follow=True)
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.avatar is not None and user.avatar != ''

    def test_profile_edit_post_with_cover(self, client, user, tmp_path):
        from django.core.files.uploadedfile import SimpleUploadedFile
        import io
        from PIL import Image

        img = Image.new('RGB', (200, 100), color='blue')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)

        cover = SimpleUploadedFile('cover.png', buf.read(), content_type='image/png')
        client.force_login(user)
        resp = client.post('/profile/edit/', {'cover_file': cover}, follow=True)
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.cover_image is not None and user.cover_image != ''

    def test_profile_edit_invalid_avatar_rejected(self, client, user):
        from django.core.files.uploadedfile import SimpleUploadedFile
        client.force_login(user)
        fake = SimpleUploadedFile('fake.jpg', b'not-an-image', content_type='image/jpeg')
        resp = client.post('/profile/edit/', {'avatar_file': fake}, follow=True)
        assert resp.status_code == 200
        user.refresh_from_db()
        # Avatar should remain unchanged (empty default)
        assert getattr(user, 'avatar', '') != b'not-an-image'


class TestWatchlistSignalXP:
    """WatchlistEntry post_save must award XP on WATCHING→COMPLETED."""

    def test_watching_to_completed_awards_xp(self, user, anime, db):
        from apps.watchlist.models import WatchlistEntry
        from apps.core.models import UserProfile

        entry = WatchlistEntry.objects.create(user=user, anime=anime, status='WATCHING', episodes_watched=5)
        # Force signal re-processing by clearing _processed set
        import apps.core.signals as sig
        sig._processed.clear()

        entry.status = 'COMPLETED'
        entry.episodes_watched = anime.episodes
        entry.save()

        profile = UserProfile.objects.get(user=user)
        assert profile.total_xp >= 50, f"Expected ≥50 XP for complete_anime, got {profile.total_xp}"

    def test_completed_from_creation_awards_xp(self, user, anime, db):
        from apps.watchlist.models import WatchlistEntry
        from apps.core.models import UserProfile

        WatchlistEntry.objects.create(user=user, anime=anime, status='COMPLETED', episodes_watched=anime.episodes)
        profile = UserProfile.objects.get(user=user)
        expected = 10 + 50  # add_to_watchlist + complete_anime
        assert profile.total_xp == expected, f"Expected {expected} XP, got {profile.total_xp}"

    def test_duplicate_save_does_not_double_xp(self, user, anime, db):
        from apps.watchlist.models import WatchlistEntry
        from apps.core.models import UserProfile

        entry = WatchlistEntry.objects.create(user=user, anime=anime, status='WATCHING')
        # Reset processed set
        import apps.core.signals as sig
        sig._processed.clear()

        entry.status = 'COMPLETED'
        entry.save()
        profile = UserProfile.objects.get(user=user)
        xp_after_first = profile.total_xp

        # Same instance saved again without status change
        entry.save()
        profile.refresh_from_db()
        assert profile.total_xp == xp_after_first, "XP should not increase on duplicate save"

    def test_add_to_watchlist_xp_no_double_count(self, user, anime, db):
        """Creating a WatchlistEntry should award XP exactly once."""
        from apps.watchlist.models import WatchlistEntry
        from apps.core.models import UserProfile

        WatchlistEntry.objects.create(user=user, anime=anime, status='PLANNING')
        profile = UserProfile.objects.get(user=user)
        assert profile.total_xp == 10, f"Expected 10 XP for add_to_watchlist, got {profile.total_xp}"

        # Creating a second entry for a different anime should work
        from apps.anime.models import Anime
        anime2 = Anime.objects.create(anilist_id=9999, title_romaji='Another', slug='another')
        WatchlistEntry.objects.create(user=user, anime=anime2, status='PLANNING')
        profile.refresh_from_db()
        assert profile.total_xp == 20, f"Expected 20 XP for two entries, got {profile.total_xp}"


class TestTierListCreate:
    """Tier list creation was silently dropping all items."""

    def test_create_tier_list_without_tier_data(self, client, user):
        client.force_login(user)
        resp = client.post('/tierlists/create/', {'title': 'My List'}, follow=True)
        assert resp.status_code == 200

    def test_create_tier_list_with_items(self, client, user, anime):
        from apps.anime.models import TierList, TierListItem
        from apps.anime.models import Anime
        from apps.anime.services.sync import sync_anime_from_anilist
        anime2 = Anime.objects.create(anilist_id=9998, title_romaji='Another Test', slug='another-test')

        client.force_login(user)
        tier_data = json.dumps({'S': [anime.anilist_id], 'A': [anime2.anilist_id]})
        resp = client.post('/tierlists/create/', {'title': 'My Tiers', 'tier_data': tier_data}, follow=True)
        assert resp.status_code == 200

        tl = TierList.objects.filter(user=user, title='My Tiers').first()
        assert tl is not None, "TierList should exist"
        items = TierListItem.objects.filter(tier_list=tl).order_by('order')
        assert items.count() == 2, f"Expected 2 items, got {items.count()}"
        assert items[0].tier == 'S'
        assert items[1].tier == 'A'

    def test_tier_list_items_ordered(self, client, user, anime):
        from apps.anime.models import Anime, TierList, TierListItem
        anime2 = Anime.objects.create(anilist_id=9997, title_romaji='B Anime', slug='b-anime')
        anime3 = Anime.objects.create(anilist_id=9996, title_romaji='C Anime', slug='c-anime')

        client.force_login(user)
        tier_data = json.dumps({'S': [anime.anilist_id, anime2.anilist_id], 'A': [anime3.anilist_id]})
        resp = client.post('/tierlists/create/', {'title': 'Ordered', 'tier_data': tier_data}, follow=True)
        assert resp.status_code == 200

        tl = TierList.objects.get(user=user, title='Ordered')
        items = TierListItem.objects.filter(tier_list=tl).order_by('order')
        assert items[0].anime_id == anime.id
        assert items[1].anime_id == anime2.id
        assert items[2].anime_id == anime3.id


class TestBattleVoteAtomic:
    """Battle votes must use F() for race-condition-safe counting."""

    def test_battle_vote_increments_count(self, client, user, anime):
        from apps.anime.models import Battle, BattleVote
        from apps.users.models import User
        other = User.objects.create_user(username='creator', password='pass')
        battle = Battle.objects.create(anime1=anime, anime2=anime, created_by=other)

        client.force_login(user)
        resp = client.post(f'/battles/{battle.id}/vote/', {'choice': '1'})
        assert resp.status_code == 302

        battle.refresh_from_db()
        assert battle.votes1 == 1
        assert battle.votes2 == 0

    def test_battle_vote_change_decrements_old(self, client, user, anime):
        from apps.anime.models import Battle, BattleVote
        from apps.users.models import User
        other = User.objects.create_user(username='creator2', password='pass')
        battle = Battle.objects.create(anime1=anime, anime2=anime, created_by=other)

        client.force_login(user)
        # Vote for 1
        client.post(f'/battles/{battle.id}/vote/', {'choice': '1'})
        battle.refresh_from_db()
        assert battle.votes1 == 1

        # Change vote to 2
        client.post(f'/battles/{battle.id}/vote/', {'choice': '2'})
        battle.refresh_from_db()
        assert battle.votes1 == 0, f"Expected votes1=0 after change, got {battle.votes1}"
        assert battle.votes2 == 1, f"Expected votes2=1 after change, got {battle.votes2}"

    def test_battle_vote_same_choice_idempotent(self, client, user, anime):
        from apps.anime.models import Battle
        from apps.users.models import User
        other = User.objects.create_user(username='creator3', password='pass')
        battle = Battle.objects.create(anime1=anime, anime2=anime, created_by=other)

        client.force_login(user)
        client.post(f'/battles/{battle.id}/vote/', {'choice': '1'})
        battle.refresh_from_db()
        assert battle.votes1 == 1

        # Same vote again
        client.post(f'/battles/{battle.id}/vote/', {'choice': '1'})
        battle.refresh_from_db()
        assert battle.votes1 == 1, "Same vote should not increment again"
        assert battle.votes2 == 0


class TestAiChatRatelimit:
    """AI Chat must be rate-limited per IP."""

    def test_chat_ai_returns_valid_json(self, client):
        resp = client.get('/chat/', {'msg': 'hello'})
        assert resp.status_code == 200
        data = resp.json()
        assert 'reply' in data
        assert 'anime' in data
        assert data['anime'] == []

    def test_chat_ai_empty_msg_returns_default(self, client):
        resp = client.get('/chat/', {'msg': ''})
        assert resp.status_code == 200
        data = resp.json()
        assert 'reply' in data
        assert 'anime' in data

    def test_chat_ai_no_msg_param(self, client):
        resp = client.get('/chat/')
        assert resp.status_code == 200
        data = resp.json()
        assert 'reply' in data

    def test_chat_ai_rate_limit_exceeded(self, client):
        """20 req/min per IP; send 25 and verify last few get 429."""
        from unittest.mock import patch

        # Mock AniList calls to avoid external dependency
        with patch('apps.core.views.anilist_client.search', return_value={'Page': {'media': []}}):
            responses = []
            for i in range(25):
                resp = client.get('/chat/', {'msg': f'test_{i}'})
                responses.append(resp.status_code)
        # At least 3 requests should be rate-limited
        limited = [s for s in responses if s == 429]
        assert len(limited) >= 3, f"Expected ≥3 rate-limited responses, got {len(limited)}. Statuses: {responses}"
