from django.urls import path, include
from rest_framework_nested import routers
from .views import ContactViewSet, ContactPersonalDetailViewSet, ContactLooseNoteViewSet

# Primary router — /api/contacts/
router = routers.DefaultRouter()
router.register(r'contacts', ContactViewSet, basename='contact')

# Nested router — /api/contacts/{contact_pk}/details/ and /notes/
contacts_router = routers.NestedDefaultRouter(router, r'contacts', lookup='contact')
contacts_router.register(r'details', ContactPersonalDetailViewSet, basename='contact-details')
contacts_router.register(r'notes', ContactLooseNoteViewSet, basename='contact-notes')

urlpatterns = [
    path('', include(router.urls)),
    path('', include(contacts_router.urls)),
]