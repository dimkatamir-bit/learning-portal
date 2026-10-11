from django.db import migrations


def add_demo_videos(apps, schema_editor):
    from courses.demo_seed import DEMO_VIDEOS, TITLE

    Module = apps.get_model("courses", "Module")
    for index, url in enumerate(DEMO_VIDEOS, 1):
        Module.objects.using(schema_editor.connection.alias).filter(
            course__title=TITLE, order=index, video_url="",
        ).update(video_url=url)


class Migration(migrations.Migration):
    dependencies = [("courses", "0004_five_modules")]
    operations = [migrations.RunPython(add_demo_videos, migrations.RunPython.noop)]
