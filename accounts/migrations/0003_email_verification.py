import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_alter_user_options_user_unique_user_email_ci")]
    operations = [
        migrations.AddField(model_name="user", name="email_verified", field=models.BooleanField(default=False, verbose_name="Email подтверждён")),
        migrations.AddField(model_name="user", name="email_verification_nonce", field=models.UUIDField(default=uuid.uuid4, editable=False)),
        migrations.AddField(model_name="user", name="email_last_sent_at", field=models.DateTimeField(blank=True, null=True, verbose_name="Последнее письмо подтверждения")),
    ]
