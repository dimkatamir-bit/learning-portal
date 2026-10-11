from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST, require_http_methods

from courses.services import course_progress, courses_with_progress

from .forms import EmailLoginForm, RegistrationForm
from .throttle import clear_attempts, is_limited, record_attempt, throttle_key
from .verification import send_verification, verification_user


def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "accounts/home.html", {
        "registration_form": RegistrationForm(),
        "login_form": EmailLoginForm(request),
        "active_tab": "register",
    })


@require_POST
def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    key = throttle_key(request, "register")
    if is_limited(key, 30):
        return render(request, "accounts/home.html", {
            "registration_form": RegistrationForm(), "login_form": EmailLoginForm(request),
            "active_tab": "register", "rate_limit_error": "Слишком много попыток. Повторите регистрацию через час.",
        }, status=429)
    record_attempt(key, 3600)
    form = RegistrationForm(request.POST)
    if form.is_valid():
        user = form.save()
        login(request, user)
        delivery = send_verification(user, request)
        if delivery == "failed":
            messages.warning(request, "Аккаунт создан, но письмо отправить не удалось. Повторите отправку позже.")
        else:
            messages.success(request, "Аккаунт создан. Подтвердите email, чтобы начать обучение.")
        return redirect("email_pending")
    return render(request, "accounts/home.html", {
        "registration_form": form,
        "login_form": EmailLoginForm(request),
        "active_tab": "register",
    }, status=400)


@require_POST
def sign_in(request):
    if request.user.is_authenticated:
        return redirect("dashboard" if request.user.email_verified or request.user.is_staff else "email_pending")
    key = throttle_key(request, "login", request.POST.get("username", ""))
    if is_limited(key, 10):
        return render(request, "accounts/home.html", {
            "registration_form": RegistrationForm(), "login_form": EmailLoginForm(request),
            "active_tab": "login", "rate_limit_error": "Слишком много попыток входа. Повторите через 15 минут.",
        }, status=429)
    form = EmailLoginForm(request, data=request.POST)
    if form.is_valid():
        clear_attempts(key)
        login(request, form.get_user())
        return redirect("dashboard" if request.user.email_verified or request.user.is_staff else "email_pending")
    record_attempt(key, 900)
    return render(request, "accounts/home.html", {
        "registration_form": RegistrationForm(),
        "login_form": form,
        "active_tab": "login",
    }, status=400)


@require_POST
def sign_out(request):
    logout(request)
    return redirect("home")


@login_required
def dashboard(request):
    courses = courses_with_progress(request.user)
    return render(request, "accounts/dashboard.html", {
        "course_cards": [(course, course_progress(request.user, course)) for course in courses],
        "certificates": request.user.certificates.exclude(pdf_file="").select_related("course").order_by("-issued_date", "-pk"),
    })


@login_required
def email_pending(request):
    if request.user.email_verified or request.user.is_staff:
        return redirect("dashboard")
    return render(request, "accounts/email_pending.html")


@login_required
@require_POST
def resend_verification(request):
    if request.user.email_verified or request.user.is_staff:
        return redirect("dashboard")
    key = throttle_key(request, "verification-send", request.user.email)
    if is_limited(key, 10):
        messages.warning(request, "Слишком много запросов. Повторите отправку через час.")
        return redirect("email_pending")
    record_attempt(key, 3600)
    result = send_verification(request.user, request)
    if result == "sent":
        messages.success(request, "Письмо подтверждения отправлено повторно.")
    elif result == "cooldown":
        messages.info(request, "Повторная отправка доступна через минуту после предыдущей.")
    elif result == "failed":
        messages.warning(request, "Не удалось отправить письмо. Повторите позже или обратитесь к администратору.")
    return redirect("email_pending")


@require_http_methods(["GET", "POST"])
def confirm_email(request, token):
    # GET only previews the action: mail security scanners must not verify an account.
    user = verification_user(token)
    if user is None:
        return render(request, "accounts/email_confirm.html", {"invalid": True}, status=400)
    if request.method == "POST":
        from .models import User
        updated = User.objects.filter(pk=user.pk, email=user.email,
                                      email_verification_nonce=user.email_verification_nonce,
                                      is_active=True, email_verified=False).update(email_verified=True)
        if not updated:
            return render(request, "accounts/email_confirm.html", {"invalid": True}, status=400)
        messages.success(request, "Email подтверждён. Теперь можно проходить курсы.")
        return redirect("dashboard" if request.user.is_authenticated and request.user.pk == user.pk else "home")
    return render(request, "accounts/email_confirm.html", {"confirmation_email": user.email})
