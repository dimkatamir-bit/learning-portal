from collections import defaultdict

from exams.models import ExamAttempt
from .models import Course, UserProgress


def employee_progress(users, course_id=None):
    """Bulk data for one row per employee; percentages match passed module exams."""
    users = list(users)
    ids = [user.pk for user in users]
    progress = list(UserProgress.objects.filter(user_id__in=ids).select_related('module__course'))
    begun = defaultdict(set)
    records = {}
    for record in progress:
        begun[record.user_id].add(record.module.course_id)
        records[(record.user_id, record.module_id)] = record
    course_ids = set().union(*begun.values()) if begun else set()
    courses = {course.pk: course for course in Course.objects.filter(pk__in=course_ids).prefetch_related('modules').order_by('pk')}
    passed = defaultdict(set)
    finals = set()
    for user_id, cid, mid, final in ExamAttempt.objects.filter(user_id__in=ids, passed=True).order_by().values_list('user_id', 'exam__course_id', 'exam__module_id', 'exam__is_final').distinct():
        if final:
            finals.add((user_id, cid))
        elif mid:
            passed[(user_id, cid)].add(mid)
    result = []
    for user in users:
        summaries = []
        for cid in sorted(begun[user.pk]):
            if course_id and cid != course_id:
                continue
            course = courses[cid]
            modules = list(course.modules.all())
            completed = sum(m.pk in passed[(user.pk, cid)] for m in modules)
            percent = round(100 * completed / len(modules)) if modules else 0
            tone = 'complete' if percent == 100 else 'advanced' if percent >= 70 else 'started' if percent else 'empty'
            next_module = next((m for m in modules if m.pk not in passed[(user.pk, cid)]), None)
            rows = []
            locked = False
            for module in modules:
                record = records.get((user.pk, module.pk))
                done = module.pk in passed[(user.pk, cid)]
                rows.append({'module': module, 'record': record, 'passed': done, 'locked': locked})
                if not done:
                    locked = True
            summaries.append({'course': course, 'completed': completed, 'total': len(modules),
                              'percent': percent, 'tone': tone, 'next_module': next_module,
                              'final_passed': (user.pk, cid) in finals, 'modules': rows})
        result.append({'employee': user, 'courses': summaries})
    return result
