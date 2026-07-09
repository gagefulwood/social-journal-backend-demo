# Migration created on 2026-06-21

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0003_event_end_timestamp_event_location_label_event_tier'),
        ('lookups', '0014_interactionmode'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='description',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='event',
            name='impact',
            field=models.CharField(blank=True, choices=[('negative', 'Negative'), ('neutral', 'Neutral'), ('positive', 'Positive')], max_length=20),
        ),
        migrations.AddField(
            model_name='event',
            name='interaction_mode',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='events', to='lookups.interactionmode'),
        ),
        migrations.AddField(
            model_name='event',
            name='mood',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='events', to='lookups.mood'),
        ),
    ]
