from django.core.management.base import BaseCommand
from django.db import transaction

from courses.demo_seed import ensure_demo
from courses.models import Course, Module
from exams.models import Choice, Exam, Question


class Command(BaseCommand):
    help = "Создаёт или восстанавливает демонстрационный курс из пяти модулей."

    @transaction.atomic
    def handle(self, *args, **options):
        course = ensure_demo(Course, Module, Exam, Question, Choice)
        self.stdout.write(self.style.SUCCESS(
            f"Готово: {course.title}; 5 модулей, 5 модульных тестов и финальный экзамен."
        ))
