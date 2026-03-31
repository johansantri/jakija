import datetime
from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache

class ActiveUserMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if request.user.is_authenticated:
            now = datetime.datetime.now()
            cache.set(f'seen_{request.user.id}', now, timeout=300)  # 5 menit


class XForwardedForMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            # ambil IP pertama dari header
            request.META['REMOTE_ADDR'] = x_forwarded_for.split(',')[0].strip()
        return self.get_response(request)
