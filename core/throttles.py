from rest_framework.throttling import BaseThrottle
from django.utils import timezone
from datetime import timedelta
from journal.models import Reflection

class ReflectionRateThrottle(BaseThrottle):
    '''
    Allows at most one Reflection per JournalEntry per 12-hour window per user.
    '''
    def allow_request(self, request, view):
        if request.method != 'POST':
            return True
        
        entry_pk = view.kwargs.get('entry_pk')
        if not entry_pk:
            return True
        
        cutoff = timezone.now() - timedelta(hours=12)
        recent = Reflection.objects.filter(
            journal_entry_id=entry_pk,
            created_timestamp__gte=cutoff,
        ).exists()

        if recent:
            self.wait_until = cutoff + timedelta(hours=12)
            return False
        return True
    
    def wait(self):
        if hasattr(self, 'wait_until'):
            delta = self.wait_until - timezone.now()
            return max(0, delta.total_seconds())
        return None