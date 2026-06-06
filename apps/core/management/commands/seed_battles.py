from django.core.management.base import BaseCommand
from apps.anime.models import Battle, Anime
from apps.anime.services.anilist import anilist_client
from apps.anime.services.sync import sync_anime_from_anilist

CURATED_BATTLES = [
    ("Naruto", "One Piece"),
    ("Attack on Titan", "Fullmetal Alchemist: Brotherhood"),
    ("Death Note", "Code Geass"),
    ("Demon Slayer", "Jujutsu Kaisen"),
    ("Steins;Gate", "Re:Zero"),
    ("Hunter x Hunter", "Yu Yu Hakusho"),
    ("Cowboy Bebop", "Samurai Champloo"),
    ("Your Name", "A Silent Voice"),
    ("Spirited Away", "Howl's Moving Castle"),
    ("One Punch Man", "Mob Psycho 100"),
    ("Violet Evergarden", "Frieren"),
    ("Chainsaw Man", "Dorohedoro"),
    ("Monster", "Psycho-Pass"),
    ("Made in Abyss", "The Promised Neverland"),
    ("Kaguya-sama", "Toradora"),
]


class Command(BaseCommand):
    help = "Seed curated battles from popular anime matchups"

    def handle(self, *args, **options):
        created_count = 0
        skipped_count = 0
        for name1, name2 in CURATED_BATTLES:
            a1 = Anime.objects.filter(title_english__iexact=name1).first() or \
                 Anime.objects.filter(title_romaji__iexact=name1).first()
            a2 = Anime.objects.filter(title_english__iexact=name2).first() or \
                 Anime.objects.filter(title_romaji__iexact=name2).first()
            if not a1:
                try:
                    data = anilist_client.search(search=name1, page=1, per_page=1)
                    media = data.get('Page', {}).get('media', [])
                    if media:
                        a1 = sync_anime_from_anilist(media[0])
                except Exception:
                    pass
            if not a2:
                try:
                    data = anilist_client.search(search=name2, page=1, per_page=1)
                    media = data.get('Page', {}).get('media', [])
                    if media:
                        a2 = sync_anime_from_anilist(media[0])
                except Exception:
                    pass
            if a1 and a2:
                _, created = Battle.objects.get_or_create(
                    anime1=a1, anime2=a2, category='versus',
                    defaults={'is_active': True},
                )
                if created:
                    created_count += 1
                    self.stdout.write(f"Created: {a1} vs {a2}")
                else:
                    skipped_count += 1
            else:
                skipped_count += 1
                self.stdout.write(f"Skipped: {name1} vs {name2} (not found)")
        self.stdout.write(self.style.SUCCESS(f"Done. Created {created_count}, skipped {skipped_count}"))
