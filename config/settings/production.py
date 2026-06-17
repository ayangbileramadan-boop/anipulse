from .base import *
from decouple import config

DEBUG = True

ALLOWED_HOSTS = ['.onrender.com', 'anipulse-80ms.onrender.com']
CSRF_TRUSTED_ORIGINS = ['https://*.onrender.com']

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

import dj_database_url
DATABASES = {
    'default': dj_database_url.config(conn_max_age=600),
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# ─── Cloudflare R2 (S3-compatible object storage) ───────────────────
R2_BUCKET = config('R2_BUCKET', default='')
R2_ACCESS_KEY = config('R2_ACCESS_KEY', default='')
R2_SECRET_KEY = config('R2_SECRET_KEY', default='')
R2_ACCOUNT_ID = config('R2_ACCOUNT_ID', default='')
R2_PUBLIC_URL = config('R2_PUBLIC_URL', default='')

# ─── AnimePahe ──────────────────────────────────────────────────────
ANIMEPAHE_BASE_URL = config('ANIMEPAHE_BASE_URL', default='https://animepahe.ru')

if R2_BUCKET and R2_ACCESS_KEY and R2_SECRET_KEY and R2_ACCOUNT_ID:
    STORAGES = {
        'default': {
            'BACKEND': 'storages.backends.s3.S3Storage',
            'OPTIONS': {
                'bucket_name': R2_BUCKET,
                'access_key': R2_ACCESS_KEY,
                'secret_key': R2_SECRET_KEY,
                'endpoint_url': f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com',
                'region_name': 'auto',
                'default_acl': 'public-read',
                'file_overwrite': False,
                'location': 'media',
            },
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
        },
    }

    if R2_PUBLIC_URL:
        AWS_S3_CUSTOM_DOMAIN = R2_PUBLIC_URL
        AWS_S3_ENDPOINT_URL = f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com'
else:
    STORAGES = {
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
        },
    }
