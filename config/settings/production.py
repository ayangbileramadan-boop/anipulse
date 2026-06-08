from urllib.parse import urlparse

from .base import *
from decouple import config

DEBUG = False

# Allow Render subdomains automatically
_render_url = config('RENDER_EXTERNAL_URL', default='')
_host = urlparse(_render_url).hostname if _render_url else ''
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='').split(',')
if _host and _host not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_host)
if '.onrender.com' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('.onrender.com')

# CSRF — trust Render's URL or .onrender.com subdomains
_csrf_origins = config('CSRF_TRUSTED_ORIGINS', default='')
if _csrf_origins:
    CSRF_TRUSTED_ORIGINS = _csrf_origins.split(',')
elif _render_url:
    CSRF_TRUSTED_ORIGINS = [_render_url.rstrip('/')]
else:
    CSRF_TRUSTED_ORIGINS = ['https://*.onrender.com']

# Security
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Static files (Whitenoise for production)
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Database
import dj_database_url
DATABASES = {
    'default': dj_database_url.config(conn_max_age=600),
}

# Cache (local memory — upgrade to Redis when needed)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
