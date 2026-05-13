from .production import *
import os

DEBUG = False
ALLOWED_HOSTS = [os.environ.get('PA_USERNAME', 'youruser') + '.pythonanywhere.com']
CSRF_TRUSTED_ORIGINS = ['https://' + ALLOWED_HOSTS[0]]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
