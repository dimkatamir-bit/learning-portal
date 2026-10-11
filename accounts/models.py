import uuid

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email обязателен")
        email = self.normalize_email(email).strip().lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True or extra_fields.get("is_superuser") is not True:
            raise ValueError("Суперпользователь должен иметь права is_staff и is_superuser")
        return self.create_user(email, password, **extra_fields)

    def get_by_natural_key(self, username):
        return self.get(email__iexact=username.strip())


class User(AbstractUser):
    username = None
    email = models.EmailField("Электронная почта", unique=True)
    country = models.CharField("Страна", max_length=100, blank=True)
    current_stage = models.CharField("Текущий этап", max_length=255, blank=True)
    email_verified = models.BooleanField("Email подтверждён", default=False)
    email_verification_nonce = models.UUIDField(default=uuid.uuid4, editable=False)
    email_last_sent_at = models.DateTimeField("Последнее письмо подтверждения", null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    class Meta:
        constraints = [models.UniqueConstraint(Lower("email"), name="unique_user_email_ci")]

    def __str__(self):
        return self.get_full_name() or self.email

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if self.pk and (update_fields is None or "email" in update_fields):
            previous = type(self).objects.filter(pk=self.pk).values_list("email", flat=True).first()
            if previous is not None and previous != self.email:
                self.email_verified = False
                self.email_verification_nonce = uuid.uuid4()
                self.email_last_sent_at = None
                if kwargs.get("update_fields") is not None:
                    kwargs["update_fields"] = set(kwargs["update_fields"]) | {
                        "email_verified", "email_verification_nonce", "email_last_sent_at",
                    }
        super().save(*args, **kwargs)
