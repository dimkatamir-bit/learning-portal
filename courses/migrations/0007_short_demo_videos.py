from django.db import migrations


def shorten_demo(apps, schema_editor):
    from courses.demo_seed import DEMO_VIDEOS, TITLE
    Module = apps.get_model("courses", "Module")
    for index, url in enumerate(DEMO_VIDEOS, 1):
        Module.objects.using(schema_editor.connection.alias).filter(
            course__title=TITLE, order=index, video_url=url.split("&end=")[0],
        ).update(video_url=url)


class Migration(migrations.Migration):
    dependencies = [("courses", "0006_video_tracking")]
    operations = [migrations.RunPython(shorten_demo, migrations.RunPython.noop)]
