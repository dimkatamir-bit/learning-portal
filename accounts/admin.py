from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Q
from django.urls import reverse
from django.utils.html import format_html

from courses.models import UserProgress

from .models import User


class UserProgressInline(admin.TabularInline):
    model = UserProgress
    fields = ("module", "status", "content_completed_at", "completed_at")
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("module__course")


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("first_name", "last_name", "country", "email", "current_stage", "email_verified", "is_active", "completed_modules")
    list_filter = ("is_active", "is_staff", "country", "email_verified", "current_stage")
    list_display_links = ("first_name", "email")
    list_per_page = 30
    save_on_top = True
    readonly_fields = ("learning_links", "email_last_sent_at", "last_login", "date_joined")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("email",)
    inlines = (UserProgressInline,)

    fieldsets = (
        (None, {"fields": ("email", "password", "email_verified", "email_last_sent_at")}),
        ("Обучение сотрудника", {"fields": ("learning_links",)}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "country", "current_stage")}),
        (_("Permissions"), {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "first_name", "last_name", "country", "current_stage", "password1", "password2"),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _completed_modules=Count("progress", filter=Q(progress__status="completed"), distinct=True),
        )

    @admin.display(description="Пройдено модулей", ordering="_completed_modules")
    def completed_modules(self, obj):
        return obj._completed_modules

    @admin.display(description="Результаты")
    def learning_links(self, obj):
        if not obj.pk:
            return "Сохраните сотрудника, чтобы открыть его результаты."
        return format_html(
            '<a href="{}">Прогресс</a> · <a href="{}?user__id__exact={}">Попытки тестов</a> · <a href="{}?user__id__exact={}">Сертификаты</a>',
            reverse("admin:progress_employee_detail", args=[obj.pk]),
            reverse("admin:exams_examattempt_changelist"), obj.pk,
            reverse("admin:certificates_certificate_changelist"), obj.pk,
        )
