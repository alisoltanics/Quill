# Adds a client-supplied idempotency key to folders so retried
# POST /api/folders requests return the original folder instead of
# creating duplicates.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0003_documentpermission'),
    ]

    operations = [
        migrations.AddField(
            model_name='folder',
            name='idempotency_key',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddConstraint(
            model_name='folder',
            constraint=models.UniqueConstraint(
                condition=models.Q(('idempotency_key__isnull', False)),
                fields=('user_id', 'idempotency_key'),
                name='uniq_folder_user_idempotency',
            ),
        ),
    ]
