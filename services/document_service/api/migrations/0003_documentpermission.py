from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_backfill_yjs_state_columns'),
    ]

    operations = [
        migrations.CreateModel(
            name='DocumentPermission',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user_email', models.EmailField(db_index=True, max_length=254)),
                ('role', models.CharField(
                    choices=[
                        ('owner', 'Owner'),
                        ('editor', 'Editor'),
                        ('viewer', 'Viewer'),
                    ],
                    default='viewer',
                    max_length=10,
                )),
                ('granted_by', models.EmailField(max_length=254)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('document', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='permissions',
                    to='api.document',
                )),
            ],
            options={
                'ordering': ['-created_at'],
                'unique_together': {('document', 'user_email')},
            },
        ),
    ]
