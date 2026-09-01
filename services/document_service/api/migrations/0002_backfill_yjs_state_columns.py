from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE api_document
                ADD COLUMN IF NOT EXISTS yjs_state TEXT NOT NULL DEFAULT '';

                ALTER TABLE api_documentversion
                ADD COLUMN IF NOT EXISTS yjs_state TEXT NOT NULL DEFAULT '';
            """,
            reverse_sql="""
                ALTER TABLE api_document
                DROP COLUMN IF EXISTS yjs_state;

                ALTER TABLE api_documentversion
                DROP COLUMN IF EXISTS yjs_state;
            """,
        ),
    ]
