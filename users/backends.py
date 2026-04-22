from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()

class EmailOrUsernameBackend(ModelBackend):
    '''
    Custom authentication backend to allow users to log in with
    either their email or their username. Checks both fields in a single
    query using Q objects.
    '''
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        
        try:
            user = User.objects.get(
                Q(email__iexact=username) | Q(username__iexact=username)
            )
        except User.DoesNotExist:
            return None
        except User.MultipleObjectsReturned:
            return None
        
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        
        return None