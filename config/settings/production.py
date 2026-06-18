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

# ─── AnimePahe ──────────────────────────────────────────────────────
ANIMEPAHE_BASE_URL = config('ANIMEPAHE_BASE_URL', default='https://animepahe.pw')

# ─── Cloudinary ─────────────────────────────────────────────────────
import cloudinary

CLOUDINARY_CLOUD_NAME = config('CLOUDINARY_CLOUD_NAME', default='dlhv9d3jo')
CLOUDINARY_API_KEY = config('CLOUDINARY_API_KEY', default='329518554126186')
CLOUDINARY_API_SECRET = config('CLOUDINARY_API_SECRET', default='EDQa0Id8gf5_Xm2Dm_8X7vxwHY8')

cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
    secure=True,
)

DEFAULT_FILE_STORAGE = 'apps.core.storage.CloudinaryImageStorage'
