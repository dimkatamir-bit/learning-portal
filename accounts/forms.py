from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import User


class RegistrationForm(UserCreationForm):
    first_name = forms.CharField(label="Имя", max_length=150)
    last_name = forms.CharField(label="Фамилия", max_length=150)
    country = forms.CharField(label="Страна", max_length=100)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("first_name", "last_name", "country", "email")
        labels = {"email": "Email"}

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"]).strip().lower()
        domain = email.rsplit("@", 1)[-1]
        if domain not in settings.REGISTRATION_EMAIL_DOMAINS:
            raise forms.ValidationError(
                "Используйте адрес с разрешённым окончанием: " + ", ".join(settings.REGISTRATION_EMAIL_DOMAINS) + "."
            )
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Этот email уже зарегистрирован.")
        return email


class EmailLoginForm(AuthenticationForm):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autofocus": True}))
