from .production import *
import os

DEBUG = False
ALLOWED_HOSTS = ['makaveli.pythonanywhere.com']
CSRF_TRUSTED_ORIGINS = ['https://makaveli.pythonanywhere.com']

# Don't HSTS all of pythonanywhere.com
SECURE_HSTS_INCLUDE_SUBDOMAINS = False

# PA terminates SSL at proxy, forwards HTTP + X-Forwarded-Proto header
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

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
