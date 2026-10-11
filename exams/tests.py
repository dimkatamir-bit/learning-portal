import tempfile
import json
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from certificates.models import Certificate
from certificates.services import _only_embedded_qr
from courses.models import Course, Module, UserProgress
from courses.demo_seed import DEMO_VIDEOS
from courses.video import youtube_embed_url

from .models import Choice, Exam, ExamAttempt, Question


class LearningFlowTests(TestCase):
    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_dir.cleanup)
        self.media_override = override_settings(MEDIA_ROOT=self.media_dir.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.user = get_user_model().objects.create_user(
            email="learner@example.test", password="TestingPassword2026!",
            first_name="Анна", last_name="Иванова", country="Казахстан",
            email_verified=True,
        )
        self.course = Course.objects.create(title="Безопасность", description="Обучение")
        self.first = Module.objects.create(course=self.course, order=1, title="Введение", content="Урок 1")
        self.second = Module.objects.create(course=self.course, order=2, title="Практика", content="Урок 2")
        self.exams = {}
        for name, module, is_final in (
            ("first", self.first, False), ("second", self.second, False), ("final", None, True),
        ):
            exam = Exam.objects.create(course=self.course, module=module, is_final=is_final)
            question = Question.objects.create(exam=exam, text="Правильный ответ?")
            yes = Choice.objects.create(question=question, text="Да", is_correct=True)
            no = Choice.objects.create(question=question, text="Нет", is_correct=False)
            self.exams[name] = (exam, question, yes, no)
        self.client.force_login(self.user)

    def answer(self, name, correct=True):
        exam, question, yes, no = self.exams[name]
        return self.client.post(reverse("take_exam", args=[exam.pk]), {
            f"question_{question.pk}": [str(yes.pk if correct else no.pk)],
        })

    def test_full_course_flow_and_private_pdf(self):
        self.assertEqual(self.client.get(reverse("module_detail", args=[self.second.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("take_exam", args=[self.exams["final"][0].pk])).status_code, 404)
        self.client.get(reverse("module_detail", args=[self.first.pk]))
        self.assertEqual(self.client.get(reverse("take_exam", args=[self.exams["first"][0].pk])).status_code, 404)
        self.client.post(reverse("complete_content", args=[self.first.pk]))
        self.assertEqual(self.answer("first", correct=False).status_code, 200)
        self.assertEqual(ExamAttempt.objects.filter(exam=self.exams["first"][0], passed=False).count(), 1)
        self.assertEqual(self.client.get(reverse("module_detail", args=[self.second.pk])).status_code, 404)
        self.assertEqual(self.answer("first").status_code, 200)
        self.assertEqual(UserProgress.objects.get(user=self.user, module=self.first).status, UserProgress.Status.COMPLETED)
        self.assertEqual(self.client.get(reverse("module_detail", args=[self.second.pk])).status_code, 200)
        self.client.post(reverse("complete_content", args=[self.second.pk]))
        self.assertEqual(self.answer("second").status_code, 200)
        self.assertEqual(self.answer("final").status_code, 200)
        certificate = Certificate.objects.get(user=self.user, course=self.course)
        self.assertRegex(certificate.certificate_number, r"^cesdrr-\d{4}-\d{6}$")
        with certificate.pdf_file.open("rb") as file:
            self.assertEqual(file.read(5), b"%PDF-")
        self.assertContains(self.client.get(reverse("dashboard")), certificate.certificate_number)
        self.assertEqual(self.client.get(reverse("certificate_download", args=[certificate.uuid])).status_code, 200)
        other = get_user_model().objects.create_user(email="other@example.test", password="TestingPassword2026!", email_verified=True)
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("certificate_download", args=[certificate.uuid])).status_code, 404)
        self.assertEqual(self.client.post(reverse("certificate_retry", args=[self.course.pk])).status_code, 404)
        self.client.force_login(self.user)
        self.assertEqual(self.answer("final").status_code, 200)
        self.assertEqual(Certificate.objects.filter(user=self.user, course=self.course).count(), 1)
        self.client.post(reverse("logout"))
        self.assertContains(self.client.get(reverse("certificate_verify", args=[certificate.uuid])), "Сертификат подлинный")
        self.assertEqual(self.client.get(reverse("certificate_download", args=[certificate.uuid])).status_code, 302)
        self.assertEqual(self.client.get(reverse("certificate_verify", args=["00000000-0000-0000-0000-000000000001"])).status_code, 404)

    def test_rejects_incomplete_and_forged_answers(self):
        exam, question, _, _ = self.exams["first"]
        self.client.get(reverse("module_detail", args=[self.first.pk]))
        self.client.post(reverse("complete_content", args=[self.first.pk]))
        url = reverse("take_exam", args=[exam.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {}).status_code, 400)
        self.assertEqual(self.client.post(url, {f"question_{question.pk}": ["999999"]}).status_code, 400)
        self.assertFalse(ExamAttempt.objects.exists())

    def test_dashboard_queries_do_not_grow_per_course(self):
        for number in range(15):
            Course.objects.create(title=f"Дополнительный курс {number}")
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(captured), 6)

    def test_pdf_fetcher_rejects_remote_and_file_urls(self):
        for url in ("https://example.test/image.png", "file:///etc/passwd"):
            with self.assertRaises(ValueError):
                _only_embedded_qr(url)

    def test_demo_command_idempotent(self):
        output = StringIO()
        Course.objects.filter(title="[ДЕМО] Безопасная работа с рабочими документами").delete()
        call_command("seed_demo_course", stdout=output)
        title = "[ДЕМО] Безопасная работа с рабочими документами"
        demo = Course.objects.get(title=title)
        self.assertEqual(demo.modules.count(), 5)
        self.assertEqual(demo.exams.count(), 6)
        questions_before = Question.objects.filter(exam__course=demo).count()
        self.assertEqual(questions_before, 25)
        call_command("seed_demo_course", stdout=output)
        self.assertEqual(Course.objects.filter(title=title).count(), 1)
        self.assertEqual(Question.objects.filter(exam__course=demo).count(), questions_before)
        Question.objects.filter(exam__course=demo).first().delete()
        call_command("seed_demo_course", stdout=output)
        self.assertEqual(demo.modules.count(), 5)

    def test_demo_is_available_after_initial_migrate(self):
        demo = Course.objects.get(title="[ДЕМО] Безопасная работа с рабочими документами")
        self.assertEqual(demo.modules.count(), 5)
        self.assertEqual(demo.exams.count(), 6)
        self.assertEqual(len(set(demo.modules.values_list("content", flat=True))), 5)
        self.assertTrue(all(exam.questions.count() >= 4 for exam in demo.exams.all()))
        self.assertEqual(list(demo.modules.values_list("video_url", flat=True)), list(DEMO_VIDEOS))

    def test_demo_player_and_module_navigation(self):
        demo = Course.objects.get(title="[ДЕМО] Безопасная работа с рабочими документами")
        first, second = list(demo.modules.all())[:2]
        response = self.client.get(reverse("module_detail", args=[first.pk]))
        self.assertContains(response, "w0ffwDYo00Q")
        self.assertContains(response, "Включить видео")
        self.assertContains(response, "Досмотрите видео")
        self.assertEqual(self.client.get(reverse("module_detail", args=[second.pk])).status_code, 404)

    def test_video_is_required_server_side_and_seek_is_rejected(self):
        demo = Course.objects.get(title="[ДЕМО] Безопасная работа с рабочими документами")
        module = demo.modules.first()
        exam = module.exam
        checkpoint = reverse("video_checkpoint", args=[module.pk])
        self.client.get(reverse("module_detail", args=[module.pk]))
        self.client.post(reverse("complete_content", args=[module.pk]))
        self.assertIsNone(UserProgress.objects.get(user=self.user, module=module).content_completed_at)
        self.assertEqual(self.client.get(reverse("take_exam", args=[exam.pk])).status_code, 404)

        start = timezone.now()
        def ping(second, event="tick", position=None):
            with patch("courses.views.timezone.now", return_value=start + timedelta(seconds=second)):
                return self.client.post(checkpoint, data=json.dumps({
                    "event": event, "position": second if position is None else position,
                    "duration": 30,
                }), content_type="application/json")

        self.assertEqual(ping(0).status_code, 200)
        self.assertEqual(ping(1, position=11).status_code, 409)
        self.assertEqual(ping(2).status_code, 200)
        self.assertEqual(ping(4).status_code, 200)
        self.assertEqual(ping(6).status_code, 200)
        self.assertEqual(ping(8).status_code, 200)
        self.assertEqual(ping(10).status_code, 200)
        self.assertFalse(ping(12, event="ended").json()["completed"])
        for second in range(14, 30, 2):
            self.assertEqual(ping(second).status_code, 200)
        self.assertTrue(ping(30, event="ended").json()["completed"])
        self.client.post(reverse("complete_content", args=[module.pk]))
        self.assertIsNotNone(UserProgress.objects.get(user=self.user, module=module).content_completed_at)
        self.assertEqual(self.client.get(reverse("take_exam", args=[exam.pk])).status_code, 200)

    def test_only_known_youtube_hosts_are_embedded(self):
        self.assertEqual(youtube_embed_url("https://youtu.be/w0ffwDYo00Q"),
                         "https://www.youtube-nocookie.com/embed/w0ffwDYo00Q")
        for url in ("https://youtube.com.evil.test/watch?v=w0ffwDYo00Q",
                    "http://youtube.com/watch?v=w0ffwDYo00Q",
                    "https://youtube.com/watch?v=invalid", "https://example.test/video"):
            self.assertEqual(youtube_embed_url(url), "")

    def test_answer_choices_are_shuffled_on_render_and_grading_uses_ids(self):
        self.client.get(reverse("module_detail", args=[self.first.pk]))
        self.client.post(reverse("complete_content", args=[self.first.pk]))
        exam, question, yes, no = self.exams["first"]
        third = Choice.objects.create(question=question, text="Другой ответ", is_correct=False)
        with patch("exams.views.SystemRandom") as rng:
            rng.return_value.shuffle.side_effect = lambda choices: choices.reverse()
            response = self.client.get(reverse("take_exam", args=[exam.pk]))
        shown = response.context["questions"][0].shuffled_choices
        self.assertEqual([choice.pk for choice in shown], [third.pk, no.pk, yes.pk])
        self.assertContains(response, "Другой ответ")
        self.assertTrue(self.answer("first").context["attempt"].passed)

    def test_certificate_can_be_retried_after_renderer_error(self):
        self.client.get(reverse("module_detail", args=[self.first.pk]))
        self.client.post(reverse("complete_content", args=[self.first.pk]))
        self.answer("first")
        self.client.get(reverse("module_detail", args=[self.second.pk]))
        self.client.post(reverse("complete_content", args=[self.second.pk]))
        self.answer("second")
        with patch("exams.views.issue_certificate", side_effect=RuntimeError("test renderer failure")):
            result = self.answer("final")
        self.assertContains(result, "PDF пока не создан")
        self.assertTrue(ExamAttempt.objects.filter(user=self.user, exam=self.exams["final"][0], passed=True).exists())
        self.assertEqual(self.client.get(reverse("certificate_retry", args=[self.course.pk])).status_code, 405)
        response = self.client.post(reverse("certificate_retry", args=[self.course.pk]))
        self.assertRedirects(response, reverse("course_detail", args=[self.course.pk]))
        self.assertTrue(Certificate.objects.get(user=self.user, course=self.course).pdf_file)
