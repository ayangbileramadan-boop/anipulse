import logging

from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class SurrogateSafeMiddleware(MiddlewareMixin):
    """Strip surrogate characters from all responses as a safety net."""

    def process_response(self, request, response):
        if hasattr(response, 'content') and isinstance(response.content, bytes):
            try:
                response.content.decode('utf-8')
            except UnicodeDecodeError:
                safe = response.content.decode('utf-8', errors='replace')
                response.content = safe.encode('utf-8')
                logger.warning('Surrogates stripped from %s %s', request.method, request.path)
        return response
