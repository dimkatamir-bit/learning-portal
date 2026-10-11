from django.contrib import messages
from django.contrib.auth.decorators import login_required
import json

from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from exams.models import ExamAttempt

from .models import Module, UserProgress
from .services import course_progress, courses_with_progress, module_accessible, passed_module_ids
from .video import youtube_embed_url
from .video_tracking import video_required, video_watched


@login_required
def course_list(request):
    courses = courses_with_progress(request.user)
    return render(request, "courses/list.html", {
        "course_cards": [(course, course_progress(request.user, course)) for course in courses],
    })


@login_required
def course_detail(request, course_id):
    course = get_object_or_404(courses_with_progress(request.user), pk=course_id)
    modules = list(course.modules.all())
    passed = passed_module_ids(request.user, course)
    first_locked = False
    module_rows = []
    for module in modules:
        locked = first_locked
        module_rows.append({"module": module, "locked": locked, "passed": module.pk in passed})
        if module.pk not in passed:
            first_locked = True
    next_module = next((row["module"] for row in module_rows if not row["locked"] and not row["passed"]), None)
    final_exam = course.exams.filter(is_final=True).first()
    return render(request, "courses/detail.html", {
        "course": course,
        "module_rows": module_rows,
        "completed_count": len(passed),
        "next_module": next_module,
        "progress": course_progress(request.user, course),
        "final_exam": final_exam,
        "final_available": course.module_total > 0 and course.module_total == course.module_passed,
        "final_passed": (course.module_total > 0 and course.module_total == course.module_passed
                         and ExamAttempt.objects.filter(user=request.user, exam__course=course,
                                                        exam__is_final=True, passed=True).exists()),
        "certificate": request.user.certificates.filter(course=course).first(),
    })


@login_required
def module_detail(request, module_id):
    module = get_object_or_404(Module.objects.select_related("course"), pk=module_id)
    if not module_accessible(request.user, module):
        raise Http404("Сначала сдайте тест предыдущего модуля.")
    progress, _ = UserProgress.objects.get_or_create(user=request.user, module=module)
    if progress.status == UserProgress.Status.NOT_STARTED:
        progress.status = UserProgress.Status.IN_PROGRESS
        progress.save(update_fields=["status"])
    exam = module.course.exams.filter(module=module, is_final=False).first()
    next_module = module.course.modules.filter(order__gt=module.order).order_by("order").first()
    return render(request, "courses/module.html", {
        "module": module, "progress": progress, "exam": exam,
        "embed_url": youtube_embed_url(module.video_url) if module.video_url else "",
        "video_watched": video_watched(progress, module),
        "next_module": next_module if progress.completed_at else None,
    })


@login_required
@require_POST
def complete_content(request, module_id):
    module = get_object_or_404(Module.objects.select_related("course"), pk=module_id)
    if not module_accessible(request.user, module):
        raise Http404("Модуль закрыт.")
    progress, _ = UserProgress.objects.get_or_create(user=request.user, module=module)
    if not video_watched(progress, module) and not progress.completed_at:
        messages.error(request, "Сначала досмотрите видео урока до конца.")
        return redirect("module_detail", module_id=module.pk)
    if not progress.content_completed_at:
        progress.content_completed_at = timezone.now()
        if progress.status == UserProgress.Status.NOT_STARTED:
            progress.status = UserProgress.Status.IN_PROGRESS
        progress.save(update_fields=["content_completed_at", "status"])
    request.user.current_stage = f"{module.course.title} — {module.title}"[:255]
    request.user.save(update_fields=["current_stage"])
    messages.success(request, "Материал отмечен как изученный. Теперь можно пройти тест.")
    return redirect("module_detail", module_id=module.pk)


@login_required
@require_POST
def video_checkpoint(request, module_id):
    module = get_object_or_404(Module.objects.select_related("course"), pk=module_id)
    if not module_accessible(request.user, module) or not video_required(module):
        raise Http404("Видео недоступно.")
    try:
        data = json.loads(request.body)
        # bool is an int in Python; accept only actual JSON numbers.
        position, duration = data["position"], data["duration"]
        if type(position) not in (int, float) or type(duration) not in (int, float):
            raise ValueError
        if not (0 <= position <= 7200 and 10 <= duration <= 7200):
            raise ValueError
        position, duration = int(position), int(duration)
        if module.video_clip_seconds:
            if duration != module.video_clip_seconds:
                return JsonResponse({"error": "Неверная длительность фрагмента."}, status=400)
        if position > duration + 1 or data.get("event") not in ("tick", "ended"):
            raise ValueError
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return JsonResponse({"error": "Неверные данные плеера."}, status=400)

    with transaction.atomic():
        progress, _ = UserProgress.objects.select_for_update().get_or_create(user=request.user, module=module)
        if progress.video_url_seen != module.video_url:
            progress.video_url_seen = module.video_url
            progress.video_position = 0
            progress.video_duration = 0
            progress.video_started_at = None
            progress.video_last_ping = None
            progress.video_completed_at = None
        if progress.video_completed_at:
            return JsonResponse({"completed": True, "position": progress.video_position})
        if progress.video_duration and abs(progress.video_duration - duration) > 2:
            return JsonResponse({"error": "Длительность видео изменилась. Обновите страницу."}, status=400)
        now = timezone.now()
        if not progress.video_started_at:
            progress.video_started_at = now
        previous = progress.video_position
        elapsed = (now - progress.video_last_ping).total_seconds() if progress.video_last_ping else 0
        # One small gap per ping is tolerated for polling/rounding, never a long jump.
        allowed = 3 if progress.video_last_ping is None else min(5, max(0, int(elapsed)) + 2)
        if position > (now - progress.video_started_at).total_seconds() + 2:
            return JsonResponse({"error": "Просмотр ещё не завершён.", "position": previous}, status=409)
        if position < previous - 2:
            progress.video_position = 0
            progress.video_started_at = now
            progress.video_last_ping = now
        elif position > previous + allowed:
            return JsonResponse({"error": "Перемотка вперёд недоступна.", "position": previous}, status=409)
        else:
            progress.video_position = max(previous, position)
            progress.video_last_ping = now
        progress.video_duration = duration
        threshold = duration if module.video_clip_seconds else duration - 2
        completed = (data["event"] == "ended" and position >= threshold
                     and progress.video_position >= threshold
                     and (not module.video_clip_seconds or
                          (now - progress.video_started_at).total_seconds() >= duration - .5))
        if completed:
            progress.video_completed_at = now
        progress.save(update_fields=["video_url_seen", "video_position", "video_duration", "video_started_at",
                                     "video_last_ping", "video_completed_at"])
    return JsonResponse({"completed": completed, "position": progress.video_position})
