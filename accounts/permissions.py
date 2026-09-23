from rest_framework.permissions import BasePermission

class IsNotBanned(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        is_banned, _ = request.user.check_ban()
        return not is_banned