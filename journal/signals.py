from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender="journal.JournalEntry")
def set_entry_immutable(sender, instance, created, **kwargs):
    '''
    Sets `is_immutable` to Ture on a JournalEntry immediately after creation
    This flag is checked by JournalEntrySerializer before allowing updates.
    Uses .update() instead of .save() to avoid a post_save loop.
    '''
    if created and not instance.is_immmutable:
        instance.__class__.objects.filter(pk=instance.pk).update(is_immutable=True)
