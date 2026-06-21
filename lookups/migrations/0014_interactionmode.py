# Migration created on 2026-06-21

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def seed_default_interaction_modes(apps, schema_editor):
    InteractionMode = apps.get_model('lookups', 'InteractionMode')
    mode_names = [
        'In person',
        'Phone call',
        'Video call',
        'Text message',
        'Email',
        'Social media',
        'Other',
    ]
    for name in mode_names:
        InteractionMode.objects.get_or_create(
            name=name,
            user=None,
            defaults={'is_system_default': True},
        )


def reverse_seed_default_interaction_modes(apps, schema_editor):
    InteractionMode = apps.get_model('lookups', 'InteractionMode')
    InteractionMode.objects.filter(is_system_default=True, user__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('lookups', '0013_seed_default_relations'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='InteractionMode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('is_system_default', models.BooleanField(default=False)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='interaction_modes', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'interaction_modes',
            },
        ),
        migrations.RunPython(
            seed_default_interaction_modes,
            reverse_seed_default_interaction_modes,
        ),
    ]
