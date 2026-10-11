import uuid

from django.conf import settings
from django.db import models

from courses.models import Course


class Certificate(models.Model):
    uuid = models.UUIDField("UUID", default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="certificates")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="certificates")
    issued_date = models.DateField("Дата выдачи", auto_now_add=True)
    pdf_file = models.FileField("PDF", upload_to="certificates/", blank=True)
    certificate_number = models.CharField("Номер сертификата", max_length=32, unique=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "course"], name="unique_certificate_per_user_course")]
        verbose_name = "Сертификат"
        verbose_name_plural = "Сертификаты"

    def __str__(self):
        return self.certificate_number
