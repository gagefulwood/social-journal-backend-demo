from django.db import migrations


def seed_lookup_defaults(apps, schema_editor):
    Mood = apps.get_model('lookups', 'Mood')
    ContextCategory = apps.get_model('lookups', 'ContextCategory')
    ClosenessScore = apps.get_model('lookups', 'ClosenessScore')
    MediaType = apps.get_model('lookups', 'MediaType')
    NoteMarker = apps.get_model('lookups', 'NoteMarker')

    # ── Moods ──────────────────────────────────────────────────────────────
    moods = [
        {'name': 'Happy',   'emoji_icon': '😊'},
        {'name': 'Neutral', 'emoji_icon': '😐'},
        {'name': 'Sad',     'emoji_icon': '😢'},
        {'name': 'Angry',   'emoji_icon': '😠'},
    ]
    for mood in moods:
        Mood.objects.get_or_create(
            name=mood['name'],
            defaults={
                'emoji_icon':        mood['emoji_icon'],
                'is_system_default': True,
                'user':              None,
            }
        )

    # ── Context Categories ─────────────────────────────────────────────────
    categories = [
        {'name': 'Social',       'color': '#4A90D9'},
        {'name': 'Professional', 'color': '#27AE60'},
        {'name': 'Family',       'color': '#E67E22'},
    ]
    for category in categories:
        ContextCategory.objects.get_or_create(
            name=category['name'],
            defaults={
                'color':             category['color'],
                'is_system_default': True,
                'user':              None,
            }
        )

    # ── Closeness Scores ───────────────────────────────────────────────────
    closeness_scores = ['High', 'Medium', 'Low']
    for score in closeness_scores:
        ClosenessScore.objects.get_or_create(
            name=score,
            defaults={'is_system_default': True}
        )

    # ── Media Types ────────────────────────────────────────────────────────
    media_types = ['IMAGE', 'VIDEO', 'AUDIO', 'DOCUMENT']
    for media_type in media_types:
        MediaType.objects.get_or_create(
            name=media_type,
            defaults={'is_system_default': True}
        )

    # ── Note Markers ───────────────────────────────────────────────────────
    note_markers = [
        {'name': 'General',   'color_hex': '#718096', 'icon_reference': 'FiFileText'},
        {'name': 'Important', 'color_hex': '#E53E3E', 'icon_reference': 'FiAlertCircle'},
        {'name': 'Reminder',  'color_hex': '#D69E2E', 'icon_reference': 'FiBell'},
    ]
    for marker in note_markers:
        NoteMarker.objects.get_or_create(
            name=marker['name'],
            defaults={
                'color_hex':         marker['color_hex'],
                'icon_reference':    marker['icon_reference'],
                'is_system_default': True,
                'user':              None,
            }
        )


def reverse_seed_lookup_defaults(apps, schema_editor):
    Mood            = apps.get_model('lookups', 'Mood')
    ContextCategory = apps.get_model('lookups', 'ContextCategory')
    ClosenessScore  = apps.get_model('lookups', 'ClosenessScore')
    MediaType       = apps.get_model('lookups', 'MediaType')
    NoteMarker      = apps.get_model('lookups', 'NoteMarker')

    Mood.objects.filter(is_system_default=True).delete()
    ContextCategory.objects.filter(is_system_default=True).delete()
    ClosenessScore.objects.filter(is_system_default=True).delete()
    MediaType.objects.filter(is_system_default=True).delete()
    NoteMarker.objects.filter(is_system_default=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('lookups', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(
            seed_lookup_defaults,
            reverse_seed_lookup_defaults
        ),
    ]