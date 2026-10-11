import base64
import io
import uuid

import qrcode
from django.conf import settings
from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.urls import reverse

from .models import Certificate


def _only_embedded_qr(url, **kwargs):
    """WeasyPrint must never fetch local files or network URLs from PDF HTML."""
    if not url.startswith("data:image/png;base64,"):
        raise ValueError("Внешние ресурсы запрещены при создании PDF")
    from weasyprint import URLFetcher

    return URLFetcher(allowed_protocols=("data",))(url)


def issue_certificate(user, course, request):
    certificate, _ = Certificate.objects.get_or_create(
        user=user, course=course,
        defaults={"certificate_number": f"PENDING-{uuid.uuid4().hex}"},
    )
    if certificate.certificate_number.startswith("PENDING-"):
        certificate.certificate_number = f"cesdrr-{certificate.issued_date.year}-{certificate.pk:06d}"
        certificate.save(update_fields=["certificate_number"])
    if certificate.pdf_file and certificate.pdf_file.storage.exists(certificate.pdf_file.name):
        return certificate

    verify_path = reverse("certificate_verify", args=[certificate.uuid])
    public_base = getattr(settings, "CERTIFICATE_BASE_URL", "").rstrip("/")
    verify_url = f"{public_base}{verify_path}" if public_base else request.build_absolute_uri(verify_path)
    qr_image = qrcode.make(verify_url)
    qr_buffer = io.BytesIO()
    qr_image.save(qr_buffer, format="PNG")
    qr_data = base64.b64encode(qr_buffer.getvalue()).decode("ascii")
    html = render_to_string("certificates/pdf.html", {
        "certificate": certificate, "qr_data": qr_data, "verify_url": verify_url,
    })
    from weasyprint import HTML

    pdf = HTML(string=html, url_fetcher=_only_embedded_qr).write_pdf()
    certificate.pdf_file.save(
        f"{certificate.certificate_number}.pdf", ContentFile(pdf), save=True,
    )
    return certificate
