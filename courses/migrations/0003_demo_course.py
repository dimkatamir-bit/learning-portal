from django.db import migrations


def seed_demo(apps, schema_editor):
    from courses.demo_seed import ensure_demo

    ensure_demo(
        apps.get_model("courses", "Course"),
        apps.get_model("courses", "Module"),
        apps.get_model("exams", "Exam"),
        apps.get_model("exams", "Question"),
        apps.get_model("exams", "Choice"),
        database=schema_editor.connection.alias,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0002_userprogress_content_completed_at"),
        ("exams", "0002_examattempt_attempt_user_pass_exam_idx"),
    ]

    operations = [migrations.RunPython(seed_demo, migrations.RunPython.noop)]
