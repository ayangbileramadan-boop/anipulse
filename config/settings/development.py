from .base import *
import os

DEBUG = True
ALLOWED_HOSTS = ['*']

# Use SQLite for local dev — set DB_ENGINE=mysql in .env for production
if os.environ.get('DB_ENGINE', 'sqlite') == 'sqlite':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
