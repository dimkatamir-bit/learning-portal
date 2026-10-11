from django.conf import settings
from django.db import models

from courses.models import Course, Module


class Exam(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="exams")
    module = models.OneToOneField(Module, on_delete=models.CASCADE, related_name="exam", null=True, blank=True)
    is_final = models.BooleanField("Финальный экзамен", default=False)
    passing_score = models.PositiveSmallIntegerField("Проходной балл, %", default=70)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(passing_score__gte=0, passing_score__lte=100), name="exam_passing_score_range"),
            models.CheckConstraint(condition=(models.Q(is_final=True, module__isnull=True) | models.Q(is_final=False, module__isnull=False)), name="exam_final_xor_module"),
            models.UniqueConstraint(fields=["course"], condition=models.Q(is_final=True), name="unique_final_exam_per_course"),
        ]
        verbose_name = "Экзамен"
        verbose_name_plural = "Экзамены"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.module_id and self.course_id and self.module.course_id != self.course_id:
            raise ValidationError({"module": "Модуль должен принадлежать курсу экзамена."})

    def __str__(self):
        return f"{self.course}: {'финальный' if self.is_final else f'модуль {self.module_id}'}"


class Question(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField("Вопрос")

    def __str__(self):
        return self.text[:80]


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    text = models.CharField("Вариант ответа", max_length=500)
    is_correct = models.BooleanField("Правильный ответ", default=False)

    def __str__(self):
        return self.text


class ExamAttempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="exam_attempts")
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="attempts")
    score = models.PositiveSmallIntegerField("Результат, %")
    passed = models.BooleanField("Сдан", default=False)
    created_at = models.DateTimeField("Дата попытки", auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [models.CheckConstraint(condition=models.Q(score__gte=0, score__lte=100), name="exam_attempt_score_range")]
        indexes = [models.Index(fields=["user", "passed", "exam"], name="attempt_user_pass_exam_idx")]
        verbose_name = "Попытка экзамена"
        verbose_name_plural = "Попытки экзамена"

    def __str__(self):
        return f"{self.user}: {self.exam} — {self.score}%"
