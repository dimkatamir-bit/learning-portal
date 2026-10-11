from django.contrib.auth import authenticate, get_user_model
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.core import mail
from unittest.mock import patch
from django.test import RequestFactory
from django.urls import reverse

from .throttle import throttle_key
from .verification import verification_token


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", PUBLIC_BASE_URL="https://portal.example.test")
class AccountFlowTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_register_login_and_admin_pages(self):
        registration = self.client.post(reverse("register"), {
            "first_name": "Анна", "last_name": "Иванова", "country": "Казахстан",
            "email": "anna@gmail.com", "password1": "TestingPassword2026!",
            "password2": "TestingPassword2026!",
        })
        self.assertRedirects(registration, reverse("email_pending"))
        user = get_user_model().objects.get(email="anna@gmail.com")
        self.assertFalse(user.email_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/email/confirm/", mail.outbox[0].body)
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("email_pending"))
        confirmation = reverse("confirm_email", args=[verification_token(user)])
        self.assertEqual(self.client.get(confirmation).status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.email_verified)  # Mail scanner GET must not confirm.
        self.assertRedirects(self.client.post(confirmation), reverse("dashboard"))
        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertEqual(self.client.post(confirmation).status_code, 400)
        self.assertEqual(user.get_full_name(), "Анна Иванова")
        self.assertEqual(user.country, "Казахстан")
        self.client.post(reverse("logout"))
        self.assertIsNotNone(authenticate(email=user.email, password="TestingPassword2026!"))
        self.assertRedirects(self.client.post(reverse("login"), {
            "username": user.email, "password": "TestingPassword2026!",
        }), reverse("dashboard"))
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

        admin = get_user_model().objects.create_superuser(email="admin@example.test", password="TestingPassword2026!")
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse("admin:accounts_user_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:accounts_user_change", args=[user.pk])).status_code, 200)

    def test_unverified_access_resend_and_expired_links(self):
        user = get_user_model().objects.create_user(email="pending@example.test", password="TestingPassword2026!")
        self.client.force_login(user)
        for url in (reverse("dashboard"), reverse("course_list"), "/exams/1/"):
            self.assertRedirects(self.client.get(url), reverse("email_pending"))
        self.assertEqual(self.client.get(reverse("resend_verification")).status_code, 405)
        self.client.post(reverse("resend_verification"))
        self.client.post(reverse("resend_verification"))
        self.assertEqual(len(mail.outbox), 1)
        token = verification_token(user)
        with patch("django.core.signing.time.time", return_value=0):
            old_token = verification_token(user)
        self.assertEqual(self.client.post(reverse("confirm_email", args=[old_token])).status_code, 400)
        self.assertEqual(self.client.post(reverse("confirm_email", args=[token + "x"])).status_code, 400)
        user.email = "changed@example.test"
        user.save()
        self.assertEqual(self.client.post(reverse("confirm_email", args=[token])).status_code, 400)

    def test_mail_failure_preserves_account_and_pending_page(self):
        with patch("accounts.verification.send_mail", side_effect=RuntimeError("mail unavailable")):
            response = self.client.post(reverse("register"), {
                "first_name": "Анна", "last_name": "Иванова", "country": "Казахстан",
                "email": "failure@gmail.com", "password1": "TestingPassword2026!",
                "password2": "TestingPassword2026!",
            })
        self.assertRedirects(response, reverse("email_pending"))
        self.assertFalse(get_user_model().objects.get(email="failure@gmail.com").email_verified)

    def test_duplicate_email_case_and_login_throttle(self):
        user = get_user_model().objects.create_user(email="Test@Example.TEST", password="TestingPassword2026!")
        self.assertEqual(user.email, "test@example.test")
        self.assertIsNotNone(authenticate(email="TEST@EXAMPLE.TEST", password="TestingPassword2026!"))
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                get_user_model().objects.create_user(email="TEST@example.test", password="TestingPassword2026!")
        for _ in range(10):
            self.assertEqual(self.client.post(reverse("login"), {
                "username": user.email, "password": "wrong-password",
            }).status_code, 400)
        self.assertEqual(self.client.post(reverse("login"), {
            "username": user.email, "password": "wrong-password",
        }).status_code, 429)

    def test_admin_login_throttle(self):
        user = get_user_model().objects.create_superuser(email="admin@example.test", password="TestingPassword2026!")
        path = reverse("admin:login")
        request = RequestFactory().post(path, {"username": user.email})
        cache.set(throttle_key(request, "admin-login", user.email), 10, 900)
        self.assertEqual(self.client.post(path, {"username": user.email, "password": "TestingPassword2026!"}).status_code, 429)

    def test_admin_does_not_need_email_verification(self):
        user = get_user_model().objects.create_superuser(email="admin@example.test", password="TestingPassword2026!")
        self.assertFalse(user.email_verified)
        self.assertRedirects(self.client.post(reverse("login"), {
            "username": user.email, "password": "TestingPassword2026!",
        }), reverse("dashboard"))
        self.assertEqual(self.client.get(reverse("course_list")).status_code, 200)
        self.assertRedirects(self.client.get(reverse("email_pending")), reverse("dashboard"))

    def test_registration_requires_exact_allowed_email_domain(self):
        from .forms import RegistrationForm
        data = {"first_name": "Анна", "last_name": "Иванова", "country": "Казахстан",
                "password1": "TestingPassword2026!", "password2": "TestingPassword2026!"}
        for email in ("Asasdasd@asdasdaf.asdasd", "user@gmail.com.evil.test", "user@fakegmail.com"):
            form = RegistrationForm({**data, "email": email})
            self.assertFalse(form.is_valid())
            self.assertIn("email", form.errors)
        for email in ("User@GMAIL.COM", "user@mail.ru", "user@yandex.ru"):
            form = RegistrationForm({**data, "email": email})
            self.assertTrue(form.is_valid(), form.errors)

    def test_admin_learning_pages_and_answer_validation(self):
        from courses.models import Course
        from exams.models import Question, Choice
        from exams.admin import ChoiceFormSet
        from django.forms.models import inlineformset_factory
        admin = get_user_model().objects.create_superuser(email="admin-ui@example.test", password="TestingPassword2026!")
        self.client.force_login(admin)
        self.assertContains(self.client.get(reverse("admin:index")), "Рабочий кабинет администратора")
        course = Course.objects.get(title__startswith="[ДЕМО]")
        module = course.modules.first()
        exam = module.exam
        question = exam.questions.first()
        for path in (
            reverse("admin:courses_course_changelist"), reverse("admin:courses_course_change", args=[course.pk]),
            reverse("admin:courses_module_changelist"), reverse("admin:courses_module_change", args=[module.pk]),
            reverse("admin:exams_exam_changelist"), reverse("admin:exams_exam_change", args=[exam.pk]),
            reverse("admin:exams_question_change", args=[question.pk]), reverse("admin:exams_examattempt_changelist"),
            reverse("admin:certificates_certificate_changelist"), reverse("admin:courses_userprogress_changelist"),
        ):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        formset = inlineformset_factory(Question, Choice, formset=ChoiceFormSet, fields=("text", "is_correct"), extra=0)
        data = {"choices-TOTAL_FORMS": "2", "choices-INITIAL_FORMS": "0", "choices-0-text": "Да", "choices-1-text": "Нет"}
        self.assertFalse(formset(data=data, instance=question, prefix="choices").is_valid())
        data["choices-0-is_correct"] = "on"
        self.assertTrue(formset(data=data, instance=question, prefix="choices").is_valid())

    def test_admin_pdf_download_requires_certificate_permission(self):
        import tempfile
        from django.core.files.base import ContentFile
        from certificates.models import Certificate
        from courses.models import Course
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            admin = get_user_model().objects.create_superuser(email="pdf-admin@example.test", password="TestingPassword2026!", first_name="Анна", last_name="Иванова", country="Казахстан")
            certificate = Certificate.objects.create(user=admin, course=Course.objects.first(), certificate_number="cesdrr-test-admin")
            certificate.pdf_file.save("admin-test.pdf", ContentFile(b"%PDF-1.4 test"))
            url = reverse("admin:certificate_admin_download", args=[certificate.pk])
            self.client.force_login(admin)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            response.close()
            preview_url = reverse("admin:certificate_admin_preview", args=[certificate.pk])
            response = self.client.get(preview_url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["X-Frame-Options"], "SAMEORIGIN")
            self.assertTrue(response["Content-Disposition"].startswith("inline;"))
            response.close()
            detail_url = reverse("admin:certificates_certificate_change", args=[certificate.pk])
            detail = self.client.get(detail_url)
            self.assertContains(detail, "Анна Иванова")
            self.assertContains(detail, "pdf-admin@example.test")
            self.assertContains(detail, "Казахстан")
            self.assertContains(detail, f'src="{preview_url}"')
            limited = get_user_model().objects.create_user(email="limited@example.test", password="TestingPassword2026!", is_staff=True)
            self.client.force_login(limited)
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.get(preview_url).status_code, 403)
            self.client.force_login(admin)
            certificate.pdf_file.storage.delete(certificate.pdf_file.name)
            self.assertContains(self.client.get(detail_url), "PDF отсутствует")
            self.assertEqual(self.client.get(preview_url).status_code, 404)
