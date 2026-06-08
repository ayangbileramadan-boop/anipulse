from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.anime.models import FavoriteAnime, Anime
from apps.watchlist.models import WatchlistEntry
from apps.anime.services.anilist import anilist_client
from apps.anime.services.sync import sync_anime_from_anilist


class Command(BaseCommand):
    help = 'Seed favorite anime for users from completed watchlist or AniList trending'

    def add_arguments(self, parser):
        parser.add_argument('--users', type=int, default=3, help='Number of users to seed')

    def handle(self, *args, **options):
        User = get_user_model()
        users = User.objects.filter(is_superuser=False).order_by('?')[:options['users']]
        if not users:
            self.stdout.write('No users found')
            return

        trending = []
        try:
            data = anilist_client.get_trending(page=1, per_page=15)
            for m in data.get('data', {}).get('Page', {}).get('media', []):
                trending.append(m)
        except Exception:
            self.stdout.write('Failed to fetch trending')

        total = 0
        for user in users:
            existing = set(FavoriteAnime.objects.filter(user=user).values_list('anime_id', flat=True))
            completed = WatchlistEntry.objects.filter(
                user=user, status='COMPLETED'
            ).exclude(anime_id__in=existing).select_related('anime').order_by('-updated_at')[:6]

            for entry in completed:
                FavoriteAnime.objects.get_or_create(user=user, anime=entry.anime)
                total += 1

            if existing or completed:
                continue

            for media in trending[:6]:
                anime = Anime.objects.filter(anilist_id=media['id']).first()
                if not anime:
                    anime = sync_anime_from_anilist(media)
                if anime and anime.id not in existing:
                    FavoriteAnime.objects.get_or_create(user=user, anime=anime)
                    total += 1
                    existing.add(anime.id)

        self.stdout.write(self.style.SUCCESS(f'Seeded {total} favorite anime entries'))
