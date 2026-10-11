from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.forms.models import BaseInlineFormSet
from django.urls import reverse
from django.utils.html import format_html

from .models import Choice, Exam, ExamAttempt, Question


class ExamForm(forms.ModelForm):
    class Meta:
        model = Exam
        fields = '__all__'

    def clean(self):
        cleaned = super().clean()
        module, course = cleaned.get('module'), cleaned.get('course')
        if cleaned.get('is_final') and module:
            self.add_error('module', 'У финального экзамена модуль не выбирается.')
        if not cleaned.get('is_final') and not module:
            self.add_error('module', 'Выберите модуль для модульного теста.')
        if module and course and module.course_id != course.pk:
            self.add_error('module', 'Модуль должен принадлежать выбранному курсу.')
        return cleaned


class QuestionInline(admin.TabularInline):
    model = Question
    fields = ('text',)
    extra = 0
    show_change_link = True


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    form = ExamForm
    list_display = ('course', 'module', 'is_final', 'passing_score', 'question_count', 'ready')
    list_filter = ('course', 'is_final')
    search_fields = ('course__title', 'module__title')
    autocomplete_fields = ('course', 'module')
    list_select_related = ('course', 'module')
    inlines = (QuestionInline,)
    save_on_top = True
    list_per_page = 30
    readonly_fields = ('ready',)
    fieldsets = (
        ('Настройка теста', {'fields': ('course', 'module', 'is_final', 'passing_score')}),
        ('Проверка готовности', {'fields': ('ready',), 'description': 'Для каждого вопроса нужны минимум два варианта и хотя бы один правильный ответ.'}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('questions__choices')

    @admin.display(description='Вопросов')
    def question_count(self, obj):
        return len(obj.questions.all()) if obj.pk else 0

    @admin.display(boolean=True, description='Готов к прохождению')
    def ready(self, obj):
        if not obj.pk:
            return False
        questions = list(obj.questions.all())
        return bool(questions) and all(len(q.choices.all()) >= 2 and any(c.is_correct for c in q.choices.all()) for q in questions)


class ChoiceFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        rows = [f.cleaned_data for f in self.forms if f.cleaned_data and not f.cleaned_data.get('DELETE') and f.cleaned_data.get('text')]
        if len(rows) < 2:
            raise ValidationError('Добавьте минимум два варианта ответа.')
        if not any(row.get('is_correct') for row in rows):
            raise ValidationError('Отметьте хотя бы один правильный вариант ответа.')


class ChoiceInline(admin.TabularInline):
    model = Choice
    formset = ChoiceFormSet
    fields = ('text', 'is_correct')
    extra = 2


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('short_text', 'exam', 'choice_count')
    list_filter = ('exam__course', 'exam__is_final')
    search_fields = ('text', 'exam__course__title', 'exam__module__title')
    autocomplete_fields = ('exam',)
    list_select_related = ('exam__course', 'exam__module')
    inlines = (ChoiceInline,)
    save_on_top = True
    list_per_page = 30
    fields = ('exam', 'text')

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_choice_count=Count('choices'))

    @admin.display(description='Вопрос')
    def short_text(self, obj):
        return obj.text[:100] + ('…' if len(obj.text) > 100 else '')

    @admin.display(description='Вариантов', ordering='_choice_count')
    def choice_count(self, obj):
        return obj._choice_count


@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = ('user', 'exam', 'score', 'passed', 'created_at')
    list_filter = ('passed', 'exam__course', 'exam__is_final', 'created_at')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'exam__course__title')
    list_select_related = ('user', 'exam__course', 'exam__module')
    readonly_fields = ('user', 'exam', 'score', 'passed', 'created_at')
    fields = readonly_fields
    date_hierarchy = 'created_at'
    list_per_page = 50

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
