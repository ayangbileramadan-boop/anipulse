import pytest
from apps.watchlist.models import WatchlistEntry, CustomList, Achievement


pytestmark = pytest.mark.django_db


class TestWatchlistEntry:
    def test_create_entry(self, user, anime):
        entry = WatchlistEntry.objects.create(user=user, anime=anime, status='WATCHING')
        assert str(entry) == f'{user.username} — {anime} (Watching)'

    def test_auto_complete_on_episode_match(self, user, anime):
        anime.episodes = 24
        anime.save()
        entry = WatchlistEntry.objects.create(
            user=user, anime=anime, status='WATCHING', episodes_watched=24
        )
        entry.save()
        entry.refresh_from_db()
        assert entry.status == 'COMPLETED'

    def test_score_default_none(self, user, anime):
        entry = WatchlistEntry.objects.create(user=user, anime=anime)
        assert entry.score is None

    def test_filter_by_status(self, user, anime):
        from apps.anime.models import Anime
        anime2 = Anime.objects.create(
            anilist_id=999, title_romaji='Test 2', slug='test-2',
        )
        WatchlistEntry.objects.create(user=user, anime=anime2, status='PLANNING')
        assert WatchlistEntry.objects.filter(user=user, status='PLANNING').count() == 1


class TestCustomList:
    def test_create_list(self, user):
        cl = CustomList.objects.create(user=user, name='Favorites')
        assert str(cl) == f'{user.username} — Favorites'

    def test_add_anime_to_list(self, user, anime):
        cl = CustomList.objects.create(user=user, name='Favorites')
        cl.anime.add(anime)
        assert anime in cl.anime.all()


class TestAchievement:
    def test_create_achievement(self, user):
        ach = Achievement.objects.create(
            user=user, key='first_anime',
            title='First Step', description='Added first anime',
        )
        assert str(ach) == f'{user.username} — First Step'

    def test_unique_key_per_user(self, user):
        Achievement.objects.create(user=user, key='test_key', title='Test')
        with pytest.raises(Exception):
            Achievement.objects.create(user=user, key='test_key', title='Duplicate')
