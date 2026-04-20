import uuid
from django.db import models
from django.conf import settings

# Create your models here.
class SocialGroup(models.Model):
    """
    A user-defined group of contacts (e.g. "Work Friends", "Family").
    activity_score is calculated by UpdateActivityScoreSignal (Sprint 4).
    """

    id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False,
        )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="social_groups"
        )

    group_name = models.CharField(max_length=150)
    activity_score = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "social_groups"

    def __str__(self):
        return f"{self.group_name} ({self.user})"

class GroupMember(models.Model):
    """
    Junction table linking a Contact to a SocialGroup.
    A contact cannot appear twice in the same group (unique_together).
    """

    id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False,
        )

    group = models.ForeignKey(
        SocialGroup, 
        on_delete=models.CASCADE, 
        related_name="members",
        )

    contact = models.ForeignKey(
        "contacts.Contact",
        on_delete=models.CASCADE,
        related_name="group_memberships"
        )

    class Meta:
        db_table = "group_members"
        unique_together = [("group", "contact")]

    def __str__(self):
        return f"{self.contact} in {self.group}"