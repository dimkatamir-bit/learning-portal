from django.contrib import admin
from django.urls import reverse, path
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils.html import format_html
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_sameorigin

from .models import Certificate


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ('certificate_number', 'user', 'course', 'issued_date', 'pdf_ready', 'preview_link', 'download_link', 'verify_link')
    search_fields = ('certificate_number', 'user__email', 'user__first_name', 'user__last_name', 'course__title')
    list_filter = ('course', 'issued_date')
    list_select_related = ('user', 'course')
    readonly_fields = ('uuid', 'user', 'course', 'issued_date', 'certificate_number', 'employee_name', 'employee_email', 'employee_country', 'preview_link', 'download_link', 'verify_link')
    fieldsets = (
        ('Сертификат', {'fields': ('certificate_number', 'course', 'issued_date', 'uuid')}),
        ('Получатель', {'fields': ('user', 'employee_name', 'employee_email', 'employee_country')}),
        ('Документ', {'fields': ('preview_link', 'download_link', 'verify_link')}),
    )
    change_form_template = 'admin/certificates/certificate/change_form.html'
    date_hierarchy = 'issued_date'
    list_per_page = 30

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'course')

    @admin.display(description='Имя и фамилия')
    def employee_name(self, obj):
        return obj.user.get_full_name() or 'Не указаны'

    @admin.display(description='Email')
    def employee_email(self, obj):
        return obj.user.email

    @admin.display(description='Страна')
    def employee_country(self, obj):
        return obj.user.country or 'Не указана'

    @admin.display(description='Просмотр документа')
    def preview_link(self, obj):
        if not obj.pdf_file:
            return 'PDF пока не создан'
        return format_html('<a href="{}" target="_blank" rel="noopener">Открыть сертификат ↗</a>', reverse('admin:certificate_admin_preview', args=[obj.pk]))

    def change_view(self, request, object_id, form_url='', extra_context=None):
        context = dict(extra_context or {})
        obj = self.get_object(request, object_id)
        if obj is not None and self.has_view_permission(request, obj):
            exists = bool(obj.pdf_file and obj.pdf_file.storage.exists(obj.pdf_file.name))
            context['certificate_preview_url'] = reverse('admin:certificate_admin_preview', args=[obj.pk]) if exists else None
            context['certificate_pdf_missing'] = not exists
        return super().change_view(request, object_id, form_url, context)

    @admin.display(boolean=True, description='PDF готов')
    def pdf_ready(self, obj):
        return bool(obj.pdf_file)

    @admin.display(description='Проверка подлинности')
    def verify_link(self, obj):
        return format_html('<a href="{}" target="_blank" rel="noopener">Открыть проверку ↗</a>', reverse('certificate_verify', args=[obj.uuid]))

    @admin.display(description='Скачать PDF')
    def download_link(self, obj):
        if not obj.pdf_file:
            return 'PDF пока не создан'
        return format_html('<a href="{}">Скачать PDF ↓</a>', reverse('admin:certificate_admin_download', args=[obj.pk]))

    def get_urls(self):
        return [
            path('<int:certificate_id>/download/', self.admin_site.admin_view(self.download_pdf), name='certificate_admin_download'),
            path('<int:certificate_id>/preview/', self.admin_site.admin_view(self.preview_pdf), name='certificate_admin_preview'),
        ] + super().get_urls()

    def download_pdf(self, request, certificate_id):
        return self.serve_pdf(request, certificate_id, attachment=True)

    @method_decorator(xframe_options_sameorigin)
    def preview_pdf(self, request, certificate_id):
        return self.serve_pdf(request, certificate_id, attachment=False)

    def serve_pdf(self, request, certificate_id, attachment):
        certificate = get_object_or_404(self.get_queryset(request), pk=certificate_id)
        if not self.has_view_permission(request, certificate):
            raise PermissionDenied
        if not certificate.pdf_file:
            raise Http404('PDF пока не создан.')
        try:
            file = certificate.pdf_file.open('rb')
        except FileNotFoundError:
            raise Http404('PDF не найден.')
        return FileResponse(file, as_attachment=attachment, filename=f'{certificate.certificate_number}.pdf', content_type='application/pdf')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
