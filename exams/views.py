import logging
from random import SystemRandom

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from certificates.services import issue_certificate
from courses.models import UserProgress
from courses.services import final_available, module_accessible
from courses.video_tracking import video_watched

from .models import Exam, ExamAttempt

logger = logging.getLogger(__name__)


def _render_exam_form(request, exam, questions, *, errors=None, status=200):
    """Mix answer positions for each display without changing Choice IDs used for grading."""
    rng = SystemRandom()
    for question in questions:
        question.shuffled_choices = list(question.choices.all())
        rng.shuffle(question.shuffled_choices)
        selected = set(request.POST.getlist(f"question_{question.pk}")) if errors else set()
        for choice in question.shuffled_choices:
            choice.selected = str(choice.pk) in selected
    return render(request, "exams/take.html", {
        "exam": exam, "questions": questions, "errors": errors or [],
    }, status=status)


def _check_access(user, exam):
    if exam.is_final:
        return final_available(user, exam.course)
    if exam.module_id is None or not module_accessible(user, exam.module):
        return False
    progress = UserProgress.objects.filter(user=user, module=exam.module,
                                           content_completed_at__isnull=False).first()
    return bool(progress and video_watched(progress, exam.module))


@login_required
@require_http_methods(["GET", "POST"])
def take_exam(request, exam_id):
    exam = get_object_or_404(Exam.objects.select_related("course", "module"), pk=exam_id)
    if not _check_access(request.user, exam):
        raise Http404("Экзамен пока недоступен.")
    questions = list(exam.questions.prefetch_related("choices").all())
    if not questions or any(len(question.choices.all()) < 2 or not any(
        choice.is_correct for choice in question.choices.all()
    ) for question in questions):
        return render(request, "exams/unavailable.html", {"exam": exam}, status=503)

    if request.method == "GET":
        return _render_exam_form(request, exam, questions)

    errors = []
    correct = 0
    for question in questions:
        choices = list(question.choices.all())
        selected_raw = request.POST.getlist(f"question_{question.pk}")
        allowed = {str(choice.pk) for choice in choices}
        if not selected_raw or len(selected_raw) != len(set(selected_raw)) or not set(selected_raw).issubset(allowed):
            errors.append("Ответьте на каждый вопрос, выбрав только предложенные варианты.")
            break
        correct_ids = {str(choice.pk) for choice in choices if choice.is_correct}
        if set(selected_raw) == correct_ids:
            correct += 1
    if errors:
        return _render_exam_form(request, exam, questions, errors=errors, status=400)

    score = round(100 * correct / len(questions))
    passed = score >= exam.passing_score
    with transaction.atomic():
        attempt = ExamAttempt.objects.create(user=request.user, exam=exam, score=score, passed=passed)
        if passed and exam.is_final:
            request.user.current_stage = f"{exam.course.title} — завершён"[:255]
            request.user.save(update_fields=["current_stage"])
        elif passed:
            progress, _ = UserProgress.objects.get_or_create(user=request.user, module=exam.module)
            progress.status = UserProgress.Status.COMPLETED
            if not progress.completed_at:
                progress.completed_at = timezone.now()
            progress.save(update_fields=["status", "completed_at"])
            next_module = exam.course.modules.filter(order__gt=exam.module.order).order_by("order").first()
            request.user.current_stage = (
                f"{exam.course.title} — {next_module.title}" if next_module else f"{exam.course.title} — финальный экзамен"
            )[:255]
            request.user.save(update_fields=["current_stage"])

    # PDF rendering may be slow; do not hold a database write transaction while it runs.
    certificate = None
    certificate_error = False
    if passed and exam.is_final:
        try:
            certificate = issue_certificate(request.user, exam.course, request)
        except Exception:
            logger.exception("Certificate generation failed for course %s", exam.course_id)
            certificate_error = True
    return render(request, "exams/result.html", {
        "exam": exam, "attempt": attempt, "certificate": certificate,
        "certificate_error": certificate_error,
    })
