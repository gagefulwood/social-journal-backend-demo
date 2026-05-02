from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('contacts', '0010_contact_profile_picture'),
        ('users', '0002_seed_groups_and_permissions'),
    ]

    operations = [
        migrations.RunSQL(
            sql='''
            DROP TABLE IF EXISTS group_members CASCADE;
            DROP TABLE IF EXISTS social_groups CASCADE;
            ''',
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
