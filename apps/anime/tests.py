import pytest
from apps.core.models import Streak
from apps.anime.models import Anime, Genre, Studio, Tag, Battle, BattleVote, TierList, TierListItem, Review


pytestmark = pytest.mark.django_db


class TestAnime:
    def test_create_anime(self):
        anime = Anime.objects.create(
            anilist_id=1, title_romaji='Test', slug='test',
            format='TV', status='FINISHED', episodes=12,
        )
        assert anime.display_title == 'Test'
        assert str(anime) == 'Test'

    def test_anime_with_english_title(self):
        anime = Anime.objects.create(
            anilist_id=2, title_romaji='Test', title_english='English Test', slug='english-test',
        )
        assert anime.display_title == 'English Test'

    def test_anime_genres(self):
        anime = Anime.objects.create(
            anilist_id=3, title_romaji='Test', slug='test-3',
        )
        genre = Genre.objects.create(name='Action')
        anime.genres.add(genre)
        assert genre in anime.genres.all()

    def test_anime_studios(self):
        anime = Anime.objects.create(
            anilist_id=4, title_romaji='Test', slug='test-4',
        )
        studio = Studio.objects.create(name='MAPPA', anilist_id=100)
        anime.studios.add(studio)
        assert studio in anime.studios.all()

    def test_anime_tags(self):
        anime = Anime.objects.create(
            anilist_id=5, title_romaji='Test', slug='test-5',
        )
        tag = Tag.objects.create(name='Shounen')
        anime.tags.add(tag)
        assert tag in anime.tags.all()


class TestStreak:
    def test_create_streak(self, user):
        s = Streak.objects.create(user=user)
        assert s.current_streak == 0
        assert s.longest_streak == 0

    def test_streak_check_first_time(self, user):
        s = Streak.objects.create(user=user)
        s.check_and_update()
        assert s.current_streak == 1

    def test_streak_consecutive(self, user):
        from datetime import date, timedelta
        s = Streak.objects.create(user=user, last_activity=date.today() - timedelta(days=1), current_streak=1)
        s.check_and_update()
        assert s.current_streak == 2

    def test_streak_broken(self, user):
        from django.utils import timezone
        s = Streak.objects.create(user=user, current_streak=5, last_activity=timezone.now().date() - timezone.timedelta(days=3))
        s.check_and_update()
        assert s.current_streak == 1


class TestBattle:
    def test_create_battle(self, anime):
        from apps.users.models import User
        user = User.objects.create_user(username='battler', password='pass')
        battle = Battle.objects.create(anime1=anime, anime2=anime, created_by=user)
        assert battle.total_votes == 0
        assert battle.pct1 == 50
        assert battle.pct2 == 50

    def test_battle_vote(self, anime, user):
        from apps.anime.models import BattleVote
        battle = Battle.objects.create(anime1=anime, anime2=anime, created_by=user)
        vote = BattleVote.objects.create(battle=battle, user=user, choice=1)
        assert BattleVote.objects.filter(battle=battle).count() == 1
        assert vote.choice == 1


class TestTierList:
    def test_create_tierlist(self, user):
        tl = TierList.objects.create(user=user, title='My Tiers')
        assert str(tl) == f'{user.username}: My Tiers'

    def test_add_item(self, user, anime):
        tl = TierList.objects.create(user=user, title='Test')
        item = TierListItem.objects.create(tier_list=tl, anime=anime, tier='S')
        assert item in tl.items.all()


class TestReview:
    def test_create_review(self, user, anime):
        review = Review.objects.create(anime=anime, user=user, rating=8, body='Great!')
        assert review.likes == 0
        assert str(review) == f'{user.username} on {anime.display_title}'

    def test_review_unique_constraint(self, user, anime):
        Review.objects.create(anime=anime, user=user, rating=8, body='Great!')
        with pytest.raises(Exception):
            Review.objects.create(anime=anime, user=user, rating=5, body='Duplicate')
