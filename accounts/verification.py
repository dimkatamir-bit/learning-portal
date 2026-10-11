import logging
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .models import User

logger = logging.getLogger(__name__)
SALT = "learning-portal.email-verification.v1"


def verification_token(user):
    return signing.dumps({"uid": user.pk, "email": user.email,
                          "nonce": str(user.email_verification_nonce)}, salt=SALT, compress=True)


def verification_user(token):
    try:
        data = signing.loads(token, salt=SALT, max_age=settings.EMAIL_VERIFICATION_MAX_AGE)
        return User.objects.get(pk=data["uid"], email=data["email"],
                                email_verification_nonce=data["nonce"], is_active=True,
                                email_verified=False)
    except (signing.BadSignature, User.DoesNotExist, KeyError, ValueError, TypeError):
        return None


def send_verification(user, request):
    """Reserve a durable per-account cooldown before contacting the mail server."""
    with transaction.atomic():
        current = User.objects.select_for_update().get(pk=user.pk)
        now = timezone.now()
        if current.email_verified:
            return "verified"
        if current.email_last_sent_at and now - current.email_last_sent_at < timedelta(seconds=60):
            return "cooldown"
        current.email_last_sent_at = now
        current.save(update_fields=["email_last_sent_at"])
    path = reverse("confirm_email", args=[verification_token(current)])
    if settings.PUBLIC_BASE_URL:
        url = settings.PUBLIC_BASE_URL.rstrip("/") + path
    elif settings.DEBUG:
        url = request.build_absolute_uri(path)
    else:
        logger.error("PUBLIC_BASE_URL is required for verification email")
        return "failed"
    try:
        sent = send_mail(
            "Подтвердите email — Learning Portal",
            render_to_string("accounts/email_verification.txt", {"user": current, "verification_url": url}),
            settings.DEFAULT_FROM_EMAIL, [current.email], fail_silently=False,
        )
        return "sent" if sent else "failed"
    except Exception:
        logger.exception("Email verification delivery failed for user %s", current.pk)
        return "failed"
