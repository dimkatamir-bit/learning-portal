from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("courses", "0005_demo_videos")]
    operations = [
        migrations.AddField(model_name="userprogress", name="video_url_seen", field=models.URLField(blank=True, verbose_name="Видео при просмотре")),
        migrations.AddField(model_name="userprogress", name="video_position", field=models.PositiveIntegerField(default=0, verbose_name="Просмотрено секунд")),
        migrations.AddField(model_name="userprogress", name="video_duration", field=models.PositiveIntegerField(default=0, verbose_name="Длительность видео")),
        migrations.AddField(model_name="userprogress", name="video_started_at", field=models.DateTimeField(blank=True, null=True, verbose_name="Начало просмотра видео")),
        migrations.AddField(model_name="userprogress", name="video_last_ping", field=models.DateTimeField(blank=True, null=True, verbose_name="Последняя проверка видео")),
        migrations.AddField(model_name="userprogress", name="video_completed_at", field=models.DateTimeField(blank=True, null=True, verbose_name="Видео просмотрено")),
    ]
