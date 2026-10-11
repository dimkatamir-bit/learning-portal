from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from exams.models import Exam, ExamAttempt
from .admin_progress import employee_progress
from .models import Course, Module, UserProgress


class EmployeeProgressAdminTests(TestCase):
    def setUp(self):
        self.employee = get_user_model().objects.create_user(
            email='learner@example.test', first_name='Анна', last_name='Иванова')
        self.admin = get_user_model().objects.create_superuser(email='admin@example.test', password='Testing2026!')
        self.course = Course.objects.create(title='Проверочный курс')
        self.modules = []
        for order in range(1, 6):
            module = Module.objects.create(course=self.course, order=order, title=f'Урок {order}')
            exam = Exam.objects.create(course=self.course, module=module)
            UserProgress.objects.create(user=self.employee, module=module,
                status=UserProgress.Status.COMPLETED if order < 5 else UserProgress.Status.IN_PROGRESS,
                completed_at=timezone.now() if order < 5 else None)
            if order < 5:
                ExamAttempt.objects.create(user=self.employee, exam=exam, score=100, passed=True)
            self.modules.append(module)
        self.client.force_login(self.admin)

    def test_one_employee_row_eighty_percent_and_course_details(self):
        # Repeated passes must not count the same module twice.
        ExamAttempt.objects.create(user=self.employee, exam=self.modules[0].exam, score=100, passed=True)
        response = self.client.get(reverse('admin:courses_userprogress_changelist'))
        self.assertContains(response, f'data-employee-id="{self.employee.pk}"', count=1)
        self.assertContains(response, 'aria-valuenow="80"')
        self.assertContains(response, 'tone-advanced')
        detail = self.client.get(reverse('admin:progress_employee_detail', args=[self.employee.pk]))
        for module in self.modules:
            self.assertContains(detail, module.title)
        self.assertContains(detail, 'В процессе')
        self.assertContains(detail, 'Завершён', count=4)
        ExamAttempt.objects.create(user=self.employee, exam=self.modules[-1].exam, score=100, passed=True)
        response = self.client.get(reverse('admin:courses_userprogress_changelist'))
        self.assertContains(response, 'aria-valuenow="100"')
        self.assertContains(response, 'tone-complete')

    def test_multiple_courses_filters_and_constant_query_count(self):
        other = Course.objects.create(title='Другой курс')
        module = Module.objects.create(course=other, order=1, title='Другой урок')
        UserProgress.objects.create(user=self.employee, module=module)
        with self.assertNumQueries(4):
            summaries = employee_progress([self.employee])[0]['courses']
        self.assertEqual(len(summaries), 2)
        response = self.client.get(reverse('admin:courses_userprogress_changelist'), {'course': self.course.pk, 'q': 'Анна'})
        self.assertEqual(len(response.context_data['rows']), 1)
        self.assertEqual(len(response.context_data['rows'][0]['courses']), 1)
        self.assertContains(response, 'aria-valuenow="80"')
        response = self.client.get(reverse('admin:courses_userprogress_changelist'), {'q': 'Неизвестный'})
        self.assertEqual(response.context_data['rows'], [])

    def test_staff_permissions_protect_progress_and_attempts(self):
        staff = get_user_model().objects.create_user(email='staff@example.test', is_staff=True)
        self.client.force_login(staff)
        urls = [reverse('admin:courses_userprogress_changelist'),
                reverse('admin:progress_employee_detail', args=[self.employee.pk])]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403)
        staff.user_permissions.add(Permission.objects.get(content_type__app_label='courses', codename='view_userprogress'))
        response = self.client.get(urls[1])
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'aria-valuenow="80"')
        self.assertNotContains(response, 'Последние 30 попыток')
        self.assertEqual(response.context_data['attempts'], [])
