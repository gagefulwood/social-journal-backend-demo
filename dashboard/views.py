from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Max
from datetime import timedelta

from events.models import Event
from contacts.models import Contact
from contacts.serializers import ContactListSerializer
from .serializers import DashboardSerializer, ActivityStatsSerializer, DecayContactSerializer

# Create your views here.
class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        upcoming_events = Event.objects.filter(date__gte=timezone.now()).order_by('date')[:5]
        recent_events = Event.objects.filter(date__lte=timezone.now()).order_by('-date')[:5]
        
        activity_stats = self.get_activity_stats()
        decay_radar = self.get_decay_radar()

        dashboard_data = {
            "upcoming_events": upcoming_events,
            "recent_events": recent_events,
            "activity_stats": activity_stats,
            "decay_radar": decay_radar,
        }

        serializer = DashboardSerializer(dashboard_data)
        return Response(serializer.data)

    def get_activity_stats(self):
        today = timezone.now()
        last_days = today - timedelta(days=30)
        prev_days = today - timedelta(days=60)

        recent_count = Event.objects.filter(date__gte=last_days).count()
        prev_count = Event.objects.filter(date__gte=prev_days, date__lt=last_days).count()

        trend_percent = 0
        if prev_count != 0:
            trend_percent = ((recent_count - prev_count) / prev_count) * 100

        return {
            "total_this_month": recent_count,
            "trend_percent": trend_percent,
        }

    def get_decay_radar(self):
        cutoff = timezone.now() - timedelta(days=30)
        contacts = Contact.objects.annotate(
            last_event=Max('eventparticipant__event__date')
        ).filter(last_event__lte=cutoff)

        decay_list = []
        for c in contacts:
            days_since = (timezone.now() - c.last_event).days if c.last_event else None
            decay_list.append({
                "contact": c, 
                "days_since_interaction": days_since,
            })
        
        return sorted(decay_list, key=lambda x: x['days_since_interaction'] or 0, reverse=True)