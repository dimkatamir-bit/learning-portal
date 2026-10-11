from django.http import HttpResponse
from django.urls import reverse
from django.shortcuts import redirect

from .throttle import clear_attempts, is_limited, record_attempt, throttle_key


class AdminLoginThrottleMiddleware:
    """Bound failed /admin/login/ posts as well as the public login form."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method != "POST" or request.path != reverse("admin:login"):
            return self.get_response(request)
        key = throttle_key(request, "admin-login", request.POST.get("username", ""))
        if is_limited(key, 10):
            return HttpResponse("Слишком много попыток входа. Повторите через 15 минут.", status=429)
        response = self.get_response(request)
        if response.status_code == 302:
            clear_attempts(key)
        elif response.status_code == 200:
            record_attempt(key, 900)
        return response


class EmailVerificationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated or request.user.email_verified or request.user.is_staff:
            return None
        allowed = {"home", "login", "register", "logout", "email_pending",
                   "resend_verification", "confirm_email", "certificate_verify"}
        if request.resolver_match and request.resolver_match.url_name in allowed:
            return None
        return redirect("email_pending")
