from rest_framework.permissions import BasePermission
from .models import ChatMembership


class IsChatMember(BasePermission):
    """
    Permission to check if request.user is a member of the given chat.
    Expect view to have self.kwargs['chat_id'] or 'pk' (for ChatViewSet).
    """

    def has_permission(self, request, view):
        chat_id = view.kwargs.get("chat_id") or view.kwargs.get("pk")
        if not chat_id:
            return False
        return ChatMembership.objects.filter(chat_id=chat_id, user=request.user).exists()
