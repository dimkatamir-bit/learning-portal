from django.db import migrations


def add_modules(apps, schema_editor):
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
    dependencies = [("courses", "0003_demo_course")]
    operations = [migrations.RunPython(add_modules, migrations.RunPython.noop)]
