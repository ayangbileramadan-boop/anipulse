from .base import *
from decouple import config

DEBUG = False
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='').split(',')

# Security
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='https://anipulse.com').split(',')

# Static files (Whitenoise for production)
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Cache (Redis for production — fallback to local memory if unavailable)
try:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': config('REDIS_URL', default='redis://127.0.0.1:6379/1'),
            'OPTIONS': {'CLIENT_CLASS': 'django_redis.client.DefaultClient'},
        }
    }
except Exception:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }

# Sentry
SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=0.1,
        send_default_pii=False,
    )
