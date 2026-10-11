from django.contrib import admin
from django.db.models import Count, Q
from django.urls import reverse, path
from django.utils.html import format_html
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from .admin_progress import employee_progress

from .models import Course, Module, UserProgress


class ModuleInline(admin.TabularInline):
    model = Module
    fields = ('order', 'title', 'video_url')
    extra = 0
    show_change_link = True
    ordering = ('order',)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'module_count', 'edit_exams')
    search_fields = ('title', 'description')
    inlines = (ModuleInline,)
    save_on_top = True
    list_per_page = 30
    fields = ('title', 'description')

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_module_count=Count('modules', distinct=True))

    @admin.display(description='Модулей', ordering='_module_count')
    def module_count(self, obj):
        return obj._module_count

    @admin.display(description='Тесты курса')
    def edit_exams(self, obj):
        return format_html('<a href="{}?course__id__exact={}">Открыть тесты →</a>', reverse('admin:exams_exam_changelist'), obj.pk)


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ('order', 'title', 'course', 'has_video', 'edit_exam')
    list_display_links = ('title',)
    list_filter = ('course',)
    search_fields = ('title', 'course__title', 'content')
    autocomplete_fields = ('course',)
    list_select_related = ('course', 'exam')
    ordering = ('course', 'order')
    save_on_top = True
    fieldsets = (
        ('Модуль', {'fields': ('course', 'order', 'title')}),
        ('Учебный материал', {'fields': ('content', 'video_url'), 'description': 'Текст отображается как обычный текст. Для 30-секундного фрагмента YouTube добавьте к ссылке &end=30.'}),
    )

    @admin.display(boolean=True, description='Видео')
    def has_video(self, obj):
        return bool(obj.video_url)

    @admin.display(description='Тест модуля')
    def edit_exam(self, obj):
        from exams.models import Exam
        try:
            exam = obj.exam
        except Exam.DoesNotExist:
            return format_html('<a href="{}?course={}&module={}">Добавить тест</a>', reverse('admin:exams_exam_add'), obj.course_id, obj.pk)
        return format_html('<a href="{}">Редактировать тест →</a>', reverse('admin:exams_exam_change', args=[exam.pk]))


@admin.register(UserProgress)
class UserProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'module', 'status', 'video_completed_at', 'completed_at')
    list_filter = ('status', 'module__course')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'module__title')
    list_select_related = ('user', 'module__course')
    readonly_fields = ('user', 'module', 'status', 'content_completed_at', 'completed_at', 'video_position', 'video_duration', 'video_completed_at')
    fields = readonly_fields
    list_per_page = 50

    def get_urls(self):
        return [path('employee/<int:user_id>/', self.admin_site.admin_view(self.employee_detail), name='progress_employee_detail')] + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        if not self.has_view_permission(request):
            raise PermissionDenied
        users = get_user_model().objects.filter(progress__isnull=False)
        query = request.GET.get('q', '').strip()
        if query:
            users = users.filter(Q(email__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query))
        course_raw = request.GET.get('course', '')
        course_id = int(course_raw) if course_raw.isdecimal() else None
        if course_id:
            users = users.filter(progress__module__course_id=course_id)
        employee_id = request.GET.get('user__id__exact', '')
        if employee_id.isdecimal():
            users = users.filter(pk=int(employee_id))
        page = Paginator(users.distinct().order_by('last_name', 'first_name', 'email'), self.list_per_page).get_page(request.GET.get('page'))
        request.current_app = self.admin_site.name
        params = request.GET.copy()
        params.pop('page', None)
        context = {**self.admin_site.each_context(request), 'opts': self.model._meta,
                   'title': 'Прогресс сотрудников', 'rows': employee_progress(page.object_list, course_id),
                   'page_obj': page, 'query': query, 'selected_course': course_id,
                   'filter_courses': Course.objects.order_by('title'), 'pagination_query': params.urlencode()}
        return TemplateResponse(request, 'admin/courses/progress_list.html', context)

    def employee_detail(self, request, user_id):
        if not self.has_view_permission(request):
            raise PermissionDenied
        user = get_object_or_404(get_user_model(), pk=user_id)
        from exams.models import ExamAttempt
        request.current_app = self.admin_site.name
        context = {**self.admin_site.each_context(request), 'opts': self.model._meta,
                   'title': 'Обучение сотрудника', 'employee': user,
                   'courses': employee_progress([user])[0]['courses'],
                   'attempts': ExamAttempt.objects.filter(user=user).select_related('exam__course', 'exam__module').order_by('-created_at', '-pk')[:30] if request.user.has_perm('exams.view_examattempt') else []}
        return TemplateResponse(request, 'admin/courses/progress_detail.html', context)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
