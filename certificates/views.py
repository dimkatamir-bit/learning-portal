import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from courses.models import Course
from exams.models import ExamAttempt

from .services import issue_certificate

from .models import Certificate

logger = logging.getLogger(__name__)


@login_required
@require_POST
def retry_certificate(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    if not ExamAttempt.objects.filter(
        user=request.user, exam__course=course, exam__is_final=True, passed=True,
    ).exists():
        raise Http404("Для выдачи сертификата сначала сдайте финальный экзамен.")
    try:
        issue_certificate(request.user, course, request)
    except Exception:
        logger.exception("Certificate retry failed for course %s", course_id)
        messages.error(request, "Не удалось создать PDF. Проверьте настройку WeasyPrint и повторите позже.")
    else:
        messages.success(request, "Сертификат готов и доступен в личном кабинете.")
    return redirect("course_detail", course_id=course.pk)


def verify_certificate(request, certificate_uuid):
    certificate = get_object_or_404(
        Certificate.objects.exclude(pdf_file="").select_related("user", "course"), uuid=certificate_uuid,
    )
    if not certificate.pdf_file.storage.exists(certificate.pdf_file.name):
        raise Http404("Сертификат пока не выдан.")
    return render(request, "certificates/verify.html", {"certificate": certificate})


@login_required
def download_certificate(request, certificate_uuid):
    certificate = get_object_or_404(Certificate, uuid=certificate_uuid, user=request.user)
    if not certificate.pdf_file or not certificate.pdf_file.storage.exists(certificate.pdf_file.name):
        raise Http404("PDF пока не создан.")
    return FileResponse(
        certificate.pdf_file.open("rb"),
        as_attachment=True,
        filename=f"{certificate.certificate_number}.pdf",
        content_type="application/pdf",
    )
