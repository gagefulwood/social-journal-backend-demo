from datetime import timedelta

from django.db.models import Count, Max
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema

from contacts.models import Contact
from core.constants import RELATIONSHIP_TREND_DORMANT, RELATIONSHIP_TREND_FADING
from events.models import Event
from journals.models import Exercise, Log, Reflection
from .serializers import DashboardSerializer

# Create your views here.
@extend_schema(responses=DashboardSerializer)
class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        heatmap_window = self._validated_heatmap_window(request)

        upcoming_events = self._get_upcoming_events(user)
        recent_events = self._get_recent_events(user)
        interaction_heatmap = self._get_interaction_heatmap(user, heatmap_window)
        
        activity_stats = self._get_activity_stats(user)
        decay_radar = self._get_decay_radar(user)

        payload = {
            "interaction_heatmap": interaction_heatmap,
            "upcoming_events": upcoming_events,
            "recent_events": recent_events,
            "activity_stats": activity_stats,
            "decay_radar": decay_radar,
        }

        serializer = DashboardSerializer(payload)
        return Response(serializer.data)

    def _validated_heatmap_window(self, request):
        raw_window = request.query_params.get("heatmap_window", "365")
        try:
            window = int(raw_window)
        except (TypeError, ValueError):
            raise ValidationError({
                "heatmap_window": "Must be a positive integer."
            })
        if window <= 0:
            raise ValidationError({
                "heatmap_window": "Must be a positive integer."
            })
        return window

    def _get_upcoming_events(self, user):
        return (
            Event.objects.filter(user=user, event_timestamp__gt=timezone.now())
            .select_related("context_category")
            .prefetch_related("participants", "logs", "reflections", "exercises")
            .order_by("event_timestamp")[:5]
        )

    def _get_recent_events(self, user):
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)
        return (
            Event.objects.filter(
                user=user,
                event_timestamp__gte=thirty_days_ago,
                event_timestamp__lte=now,
            )
            .select_related("context_category")
            .prefetch_related("participants", "logs", "reflections", "exercises")
            .order_by("-event_timestamp")[:5]
        )

    def _get_interaction_heatmap(self, user, window):
        today = timezone.localdate()
        start_date = today - timedelta(days=window - 1)
        start_timestamp = timezone.make_aware(
            timezone.datetime.combine(start_date, timezone.datetime.min.time())
        )
        end_timestamp = timezone.make_aware(
            timezone.datetime.combine(
                today + timedelta(days=1),
                timezone.datetime.min.time(),
            )
        )
        counts = {
            row["event_date"]: row["count"]
            for row in (
                Event.objects.filter(
                    user=user,
                    event_timestamp__gte=start_timestamp,
                    event_timestamp__lt=end_timestamp,
                )
                .annotate(event_date=TruncDate("event_timestamp"))
                .values("event_date")
                .annotate(count=Count("id"))
            )
        }
        return [
            {
                "date": start_date + timedelta(days=offset),
                "count": counts.get(start_date + timedelta(days=offset), 0),
            }
            for offset in range(window)
        ]

    def _get_activity_stats(self, user):
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)

        log_count = Log.objects.for_user(user).count()
        reflection_count = Reflection.objects.for_user(user).count()
        exercise_count = Exercise.objects.for_user(user).count()
        log_30d_count = Log.objects.for_user(user).filter(
            created_timestamp__gte=thirty_days_ago,
        ).count()
        reflection_30d_count = Reflection.objects.for_user(user).filter(
            created_timestamp__gte=thirty_days_ago,
        ).count()
        exercise_30d_count = Exercise.objects.for_user(user).filter(
            created_timestamp__gte=thirty_days_ago,
        ).count()

        return {
            "entries_total": log_count + reflection_count + exercise_count,
            "entries_30d": log_30d_count + reflection_30d_count + exercise_30d_count,
            "entries_by_kind_30d": {
                "log": log_30d_count,
                "reflection": reflection_30d_count,
                "exercise": exercise_30d_count,
            },
            "events_30d": Event.objects.filter(
                user=user,
                event_timestamp__gte=thirty_days_ago,
                event_timestamp__lte=now,
            ).count(),
            "current_streak_days": self._get_current_streak_days(user),
        }

    def _get_current_streak_days(self, user):
        entry_dates = set()
        for model in (Log, Reflection, Exercise):
            entry_dates.update(
                model.objects.for_user(user)
                .annotate(entry_date=TruncDate("created_timestamp"))
                .values_list("entry_date", flat=True)
            )

        today = timezone.localdate()
        streak = 0
        current_date = today
        while current_date in entry_dates:
            streak += 1
            current_date -= timedelta(days=1)
        return streak

    def _get_decay_radar(self, user):
        now = timezone.now()
        results = []

        contacts = (
            Contact.objects.for_user(user)
            .filter(
                relationship_trend__in=[
                    RELATIONSHIP_TREND_FADING,
                    RELATIONSHIP_TREND_DORMANT,
                ],
                events_participants__isnull=False,
            )
            .annotate(
                last_interaction_date=Max('events_participants__event__event_timestamp')
            )
            .filter(last_interaction_date__isnull=False)
            .order_by(
                '-connection_strength',
                'last_interaction_date',
                'first_name',
                'last_name',
            )[:10]
        )
        for contact in contacts:
            last_interaction_date = contact.last_interaction_date
            results.append({
                "contact_id": contact.id,
                "name": str(contact),
                "last_interaction_date": last_interaction_date,
                "days_since": (now - last_interaction_date).days,
                "relationship_trend": contact.relationship_trend,
                "connection_strength": contact.connection_strength,
            })

        return results
