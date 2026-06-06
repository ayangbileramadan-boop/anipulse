from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.anime.models import SocialPost
from apps.anime.services.anilist import anilist_client

SYSTEM_POSTS = [
    "🔥 **{title}** is trending! Are you watching it yet?",
    "📺 Just dropped: **{title}** — add it to your watchlist!",
    "⭐ **{title}** has an average score of **{score}/100** on AniList!",
    "🎬 **{title}** — {format} with **{episodes}** episodes. Binge-worthy?",
    "💬 What do you think of **{title}**? Drop your thoughts below!",
    "📈 **{title}** is blowing up with **{popularity}** users watching!",
    "🏆 **{title}** — {status}. One of the greats!",
    "🌟 Did you catch **{title}**? It's got **{favourites}** favourites!",
]

User = get_user_model()


class Command(BaseCommand):
    help = "Seed social feed with system posts from AniList trending"

    def handle(self, *args, **options):
        try:
            data = anilist_client.get_trending(page=1, per_page=15)
            media_list = data.get('Page', {}).get('media', [])
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"AniList fetch failed: {e}"))
            return

        admin, _ = User.objects.get_or_create(
            username='anipulse',
            defaults={'is_staff': True},
        )

        created = 0
        import random
        for media in media_list:
            title = media.get('title', {})
            title_str = title.get('english') or title.get('romaji') or 'Unknown'
            for tmpl in random.sample(SYSTEM_POSTS, min(2, len(SYSTEM_POSTS))):
                body = tmpl.format(
                    title=title_str,
                    score=media.get('averageScore', 'N/A'),
                    format=media.get('format', 'Anime'),
                    episodes=media.get('episodes', '?'),
                    popularity=media.get('popularity', 0),
                    status=media.get('status', 'Unknown'),
                    favourites=media.get('favourites', 0),
                )
                from apps.anime.models import Anime
                anime_obj = Anime.objects.filter(anilist_id=media.get('id')).first()
                defaults = {}
                if anime_obj:
                    defaults['anime'] = anime_obj
                _, c = SocialPost.objects.get_or_create(
                    user=admin,
                    body=body,
                    defaults=defaults,
                )
                if c:
                    created += 1

        self.stdout.write(self.style.SUCCESS(f"Seeded {created} system posts"))
