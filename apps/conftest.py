import pytest
from django.contrib.auth import get_user_model
from apps.core.models import Streak
from apps.anime.models import Anime, Genre
from apps.watchlist.models import WatchlistEntry


@pytest.fixture
def user(db):
    User = get_user_model()
    return User.objects.create_user(username='testuser', password='testpass123')


@pytest.fixture
def other_user(db):
    User = get_user_model()
    return User.objects.create_user(username='otheruser', password='testpass123')


@pytest.fixture
def genre(db):
    return Genre.objects.create(name='Action')


@pytest.fixture
def anime(db, genre):
    a = Anime.objects.create(
        anilist_id=1,
        title_romaji='Test Anime',
        title_english='Test Anime',
        slug='test-anime',
        format='TV',
        status='FINISHED',
        episodes=24,
        duration=24,
        average_score=80,
        popularity=10000,
    )
    a.genres.add(genre)
    return a


@pytest.fixture
def watchlist_entry(db, user, anime):
    return WatchlistEntry.objects.create(
        user=user,
        anime=anime,
        status='WATCHING',
        episodes_watched=12,
    )


@pytest.fixture
def streak(db, user):
    return Streak.objects.create(user=user)
