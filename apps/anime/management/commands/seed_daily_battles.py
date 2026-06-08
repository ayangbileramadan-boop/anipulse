from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.anime.models import Battle, Anime
from apps.anime.services.anilist import anilist_client
from apps.anime.services.sync import sync_anime_from_anilist


class Command(BaseCommand):
    help = 'Create daily featured battles from AniList trending/top anime'

    def handle(self, *args, **options):
        now = timezone.now()
        end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        existing = Battle.objects.filter(
            is_active=True, is_daily_featured=True,
            created_at__date=now.date(),
        ).count()
        if existing >= 3:
            self.stdout.write(f'Already have {existing} daily battles today, skipping')
            return

        anime_pool = []
        try:
            data = anilist_client.get_trending(page=1, per_page=20)
            for m in data.get('data', {}).get('Page', {}).get('media', []):
                anime_pool.append(m)
        except Exception:
            self.stdout.write('Failed to fetch trending')

        if len(anime_pool) < 20:
            try:
                data = anilist_client.get_popular_this_season(anime=False, page=1, per_page=20)
                for m in data.get('data', {}).get('Page', {}).get('media', []):
                    if m not in anime_pool:
                        anime_pool.append(m)
            except Exception:
                pass

        if len(anime_pool) < 6:
            self.stdout.write('Not enough anime to create battles')
            return

        existing_anime_ids = set(Battle.objects.filter(
            is_active=True, is_daily_featured=True,
            created_at__date=now.date(),
        ).values_list('anime1_id', 'anime2_id'))
        existing_ids = set()
        for pair in existing_anime_ids:
            existing_ids.add(pair[0])
            existing_ids.add(pair[1])

        imported = {}
        def get_anime(media):
            aid = media['id']
            if aid in imported:
                return imported[aid]
            obj = Anime.objects.filter(anilist_id=aid).first()
            if not obj:
                obj = sync_anime_from_anilist(media)
            imported[aid] = obj
            return obj

        matchups = [
            (0, 1), (2, 3), (4, 5),
            (6, 7), (8, 9), (10, 11),
        ]

        created_count = 0
        for i, j in matchups:
            if created_count >= 5:
                break
            if i >= len(anime_pool) or j >= len(anime_pool):
                continue
            m1, m2 = anime_pool[i], anime_pool[j]
            if m1['id'] in existing_ids or m2['id'] in existing_ids:
                continue
            a1 = get_anime(m1)
            a2 = get_anime(m2)
            if not a1 or not a2:
                continue
            _, created = Battle.objects.get_or_create(
                anime1=a1, anime2=a2,
                defaults={
                    'is_active': True,
                    'is_daily_featured': True,
                    'expires_at': end_of_day,
                    'category': 'versus',
                },
            )
            if created:
                created_count += 1
                existing_ids.add(m1['id'])
                existing_ids.add(m2['id'])
                self.stdout.write(f'Created: {a1} vs {a2}')

        self.stdout.write(self.style.SUCCESS(
            f'Done. Created {created_count} daily battles'
        ))
