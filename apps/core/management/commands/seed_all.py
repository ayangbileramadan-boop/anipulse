from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Run all seed commands for demo data'

    def handle(self, *args, **options):
        self.stdout.write('Seeding favorites...')
        try:
            call_command('seed_favorites', '--users', '3')
        except Exception as e:
            self.stdout.write(f'Skipped favorites: {e}')

        self.stdout.write('Seeding daily battles...')
        try:
            call_command('seed_daily_battles')
        except Exception as e:
            self.stdout.write(f'Skipped battles: {e}')

        self.stdout.write('Seeding feed posts...')
        try:
            call_command('seed_feed')
        except Exception as e:
            self.stdout.write(f'Skipped feed: {e}')

        self.stdout.write(self.style.SUCCESS('All seeding complete'))
