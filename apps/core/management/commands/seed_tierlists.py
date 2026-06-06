from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.anime.models import TierList, TierListItem, Anime
from apps.anime.services.anilist import anilist_client
from apps.anime.services.sync import sync_anime_from_anilist

SEED_TIERS = [
    {
        'title': 'Greatest of All Time',
        'tiers': {
            'S': ['Attack on Titan', 'Fullmetal Alchemist: Brotherhood', 'Steins;Gate'],
            'A': ['Death Note', 'Cowboy Bebop', 'Hunter x Hunter'],
            'B': ['One Punch Man', 'Demon Slayer', 'Jujutsu Kaisen'],
            'C': ['Tokyo Ghoul', 'Sword Art Online'],
            'D': ['The Promised Neverland S2'],
            'F': ['School Days'],
        },
    },
    {
        'title': 'Best Action Anime',
        'tiers': {
            'S': ['Attack on Titan', 'Jujutsu Kaisen', 'One Punch Man'],
            'A': ['Demon Slayer', 'Chainsaw Man', 'My Hero Academia'],
            'B': ['Naruto', 'Bleach', 'Black Clover'],
            'C': ['Fairy Tail', 'Sword Art Online'],
            'D': ['The Seven Deadly Sins'],
            'F': ['Big Order'],
        },
    },
]

User = get_user_model()


class Command(BaseCommand):
    help = "Seed curated tier lists"

    def handle(self, *args, **options):
        admin, _ = User.objects.get_or_create(
            username='anipulse',
            defaults={'is_staff': True},
        )

        created_count = 0
        import string, random

        for data in SEED_TIERS:
            slug = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
            tl, created = TierList.objects.get_or_create(
                user=admin,
                title=data['title'],
                defaults={'slug': slug, 'is_public': True},
            )
            if not created:
                self.stdout.write(f"Skipped existing: {data['title']}")
                continue

            order = 0
            for tier_label, titles in data['tiers'].items():
                for title in titles:
                    anime = Anime.objects.filter(title_english__iexact=title).first() or \
                            Anime.objects.filter(title_romaji__iexact=title).first()
                    if not anime:
                        try:
                            d = anilist_client.search(search=title, page=1, per_page=1)
                            m = d.get('Page', {}).get('media', [])
                            if m:
                                anime = sync_anime_from_anilist(m[0])
                        except Exception:
                            pass
                    if anime:
                        TierListItem.objects.create(
                            tier_list=tl, anime=anime,
                            tier=tier_label, order=order,
                        )
                        order += 1
            created_count += 1
            self.stdout.write(f"Created tier list: {data['title']}")

        self.stdout.write(self.style.SUCCESS(f"Done. Created {created_count} tier lists"))
