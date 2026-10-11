from django.conf import settings
from django.db import models


class Course(models.Model):
    title = models.CharField("Название", max_length=255)
    description = models.TextField("Описание", blank=True)

    class Meta:
        verbose_name = "Курс"
        verbose_name_plural = "Курсы"

    def __str__(self):
        return self.title


class Module(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules")
    order = models.PositiveIntegerField("Порядковый номер")
    title = models.CharField("Название", max_length=255)
    content = models.TextField("Текст урока", blank=True)
    video_url = models.URLField("Ссылка на видео", blank=True)

    @property
    def video_clip_seconds(self):
        from .video import video_clip_seconds
        return video_clip_seconds(self.video_url)

    class Meta:
        ordering = ["order", "pk"]
        constraints = [models.UniqueConstraint(fields=["course", "order"], name="unique_module_order_per_course")]
        verbose_name = "Модуль"
        verbose_name_plural = "Модули"

    def __str__(self):
        return f"{self.course}: {self.order}. {self.title}"


class UserProgress(models.Model):
    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Не начат"
        IN_PROGRESS = "in_progress", "В процессе"
        COMPLETED = "completed", "Завершён"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="progress")
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="user_progress")
    status = models.CharField("Статус", max_length=16, choices=Status.choices, default=Status.NOT_STARTED)
    content_completed_at = models.DateTimeField("Материал изучен", null=True, blank=True)
    completed_at = models.DateTimeField("Дата завершения", null=True, blank=True)
    video_url_seen = models.URLField("Видео при просмотре", blank=True)
    video_position = models.PositiveIntegerField("Просмотрено секунд", default=0)
    video_duration = models.PositiveIntegerField("Длительность видео", default=0)
    video_started_at = models.DateTimeField("Начало просмотра видео", null=True, blank=True)
    video_last_ping = models.DateTimeField("Последняя проверка видео", null=True, blank=True)
    video_completed_at = models.DateTimeField("Видео просмотрено", null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "module"], name="unique_user_module_progress")]
        verbose_name = "Прогресс"
        verbose_name_plural = "Прогресс"

    def __str__(self):
        return f"{self.user} — {self.module}: {self.get_status_display()}"
