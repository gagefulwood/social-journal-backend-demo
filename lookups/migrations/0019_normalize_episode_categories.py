from django.db import migrations


CATEGORY_RENAMES = (
    (
        'stress_response',
        'Stress response',
        'involuntary_response',
        'Involuntary response',
        'activity',
        '#d8cdf7',
    ),
    (
        'sensory_overload',
        'Sensory overload',
        'symptoms',
        'Symptoms',
        'waves',
        '#c9dcf6',
    ),
    (
        'energy_state',
        'Energy state',
        'mood',
        'Mood',
        'battery',
        '#d8ead9',
    ),
)


def normalize_episode_categories(apps, schema_editor):
    category = apps.get_model('lookups', 'EpisodeCategory')
    for old_code, _, new_code, new_name, icon, color in CATEGORY_RENAMES:
        row = category.objects.filter(
            code=old_code,
            is_system_default=True,
        ).first()
        if row:
            row.code = new_code
            row.name = new_name
            row.icon_reference = icon
            row.color = color
            row.save(
                update_fields=['code', 'name', 'icon_reference', 'color']
            )
        else:
            category.objects.update_or_create(
                code=new_code,
                is_system_default=True,
                defaults={
                    'user': None,
                    'name': new_name,
                    'icon_reference': icon,
                    'color': color,
                },
            )


def restore_previous_episode_categories(apps, schema_editor):
    category = apps.get_model('lookups', 'EpisodeCategory')
    for old_code, old_name, new_code, _, icon, color in CATEGORY_RENAMES:
        row = category.objects.filter(
            code=new_code,
            is_system_default=True,
        ).first()
        if row:
            row.code = old_code
            row.name = old_name
            row.icon_reference = icon
            row.color = color
            row.save(
                update_fields=['code', 'name', 'icon_reference', 'color']
            )


class Migration(migrations.Migration):
    dependencies = [
        ('lookups', '0018_emotionstate_episodecategory_episodecharacteristic_and_more'),
    ]

    operations = [
        migrations.RunPython(
            normalize_episode_categories,
            restore_previous_episode_categories,
        ),
    ]
