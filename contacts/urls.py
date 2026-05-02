from django.urls import path, include
from rest_framework_nested import routers
from .views import ContactViewSet, FactViewSet, ObservationViewSet

# Primary router — /api/contacts/
router = routers.DefaultRouter()
router.register(r'contacts', ContactViewSet, basename='contact')

# Nested router — /api/contacts/{contact_pk}/facts/ and /observations/
contacts_router = routers.NestedDefaultRouter(router, r'contacts', lookup='contact')
contacts_router.register(r'facts', FactViewSet, basename='contact-facts')
contacts_router.register(r'observations', ObservationViewSet, basename='contact-observations')

urlpatterns = [
    path('', include(router.urls)),
    path('', include(contacts_router.urls)),
]
