from datetime import timedelta

from django.db.models import Max
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema

from contacts.models import Contact
from core.constants import RELATIONSHIP_TREND_DORMANT, RELATIONSHIP_TREND_FADING
from events.models import Event
from .serializers import DashboardSerializer

# Create your views here.
@extend_schema(responses=DashboardSerializer)
class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user

        upcoming_events = Event.objects.upcoming(user)
        recent_events = Event.objects.recent(user)
        
        activity_stats = self._get_activity_stats(user)
        decay_radar = self._get_decay_radar(user)

        payload = {
            "upcoming_events": upcoming_events,
            "recent_events": recent_events,
            "activity_stats": activity_stats,
            "decay_radar": decay_radar,
        }

        serializer = DashboardSerializer(payload)
        return Response(serializer.data)

    def _get_activity_stats(self, user):
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)
        sixty_days_ago = now - timedelta(days=60)

        current_count = Event.objects.filter(
            user=user, event_timestamp__gte=thirty_days_ago, event_timestamp__lte=now
        ).count()

        previous_count = Event.objects.filter(
            user=user, event_timestamp__gte=sixty_days_ago, event_timestamp__lt=thirty_days_ago
        ).count()

        if previous_count == 0:
            trend_percent = 100.0 if current_count > 0 else 0.0
        else:
            trend_percent = round(((current_count - previous_count) / previous_count) * 100, 1)

        return {
            "total_this_month": current_count,
            "trend_percent": trend_percent
        }

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
