from django.db.models import Count, Q

from .models import Course
from exams.models import ExamAttempt


def courses_with_progress(user):
    """One grouped query for a catalogue of any size."""
    return Course.objects.annotate(
        module_total=Count("modules", distinct=True),
        module_passed=Count(
            "modules", filter=Q(modules__exam__attempts__user=user,
                                 modules__exam__attempts__passed=True), distinct=True,
        ),
    ).order_by("pk")


def passed_module_ids(user, course):
    return set(ExamAttempt.objects.filter(
        user=user, exam__course=course, exam__is_final=False, passed=True,
    ).values_list("exam__module_id", flat=True))


def module_accessible(user, module):
    preceding = set(module.course.modules.filter(order__lt=module.order).values_list("pk", flat=True))
    return preceding.issubset(passed_module_ids(user, module.course))


def final_available(user, course):
    module_ids = set(course.modules.values_list("pk", flat=True))
    return bool(module_ids) and module_ids.issubset(passed_module_ids(user, course))


def course_progress(user, course):
    if hasattr(course, "module_total") and hasattr(course, "module_passed"):
        return round(100 * course.module_passed / course.module_total) if course.module_total else 0
    total = course.modules.count()
    return round(100 * len(passed_module_ids(user, course)) / total) if total else 0
