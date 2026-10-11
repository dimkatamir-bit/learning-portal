import hashlib

from django.conf import settings
from django.core.cache import cache


def throttle_key(request, action, identifier=""):
    # Do not store email or IP in the cache key in plain text.
    remote = request.META.get("REMOTE_ADDR", "unknown")
    raw = f"{settings.SECRET_KEY}|{action}|{remote}|{identifier.strip().casefold()}"
    return "throttle:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_limited(key, limit):
    return cache.get(key, 0) >= limit


def record_attempt(key, seconds):
    cache.add(key, 0, timeout=seconds)
    cache.incr(key)


def clear_attempts(key):
    cache.delete(key)
