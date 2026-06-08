import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.core.management import call_command

User = get_user_model()


class Command(BaseCommand):
    help = 'Run all seed commands for demo data'

    def handle(self, *args, **options):
        # Create admin from env vars (set in Render dashboard)
        admin_user = os.environ.get('ADMIN_USERNAME', '')
        admin_pass = os.environ.get('ADMIN_PASSWORD', '')
        admin_email = os.environ.get('ADMIN_EMAIL', '')
        if admin_user and admin_pass and admin_email:
            if not User.objects.filter(username=admin_user).exists():
                User.objects.create_superuser(admin_user, admin_email, admin_pass)
                self.stdout.write(f'Created admin: {admin_user}')
            else:
                self.stdout.write(f'Admin {admin_user} already exists')

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
