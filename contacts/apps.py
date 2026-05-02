from django.apps import AppConfig


class ContactsConfig(AppConfig):
    '''
    Contacts app config, registers interaction metric signals on app ready.
    '''
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'contacts'

    def ready(self):
        import contacts.signals
