from rest_framework.permissions import BasePermission

class IsOwner(BasePermission):
    '''
    Object-level permission to restrict access to owners of a record.
    Checks obj.user == request.user for any model with a user foreign key,
    but returns 403 for any unauthenticated user access attempts of another users data
    '''
    message = 'You do not have permission to access this resource.'

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        return obj.user == request.user