from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ChatViewSet, MessageListCreateView, MarkAsReadView, ReactionView, 
    ChatWaveView, AuthView, UserListView, UserMeView
)

router = DefaultRouter(trailing_slash=False)
router.register(r"chats", ChatViewSet, basename="chat")

urlpatterns = [
    path("", include(router.urls)),
    path("me", UserMeView.as_view(), name="user-me"),
    path("users/", UserListView.as_view(), name="user-list"),
    # Messages
    path("chats/<str:chat_id>/messages", MessageListCreateView.as_view(), name="message-list"),
    # Mark as read
    path("chats/<str:chat_id>/messages/<str:message_id>/read", MarkAsReadView.as_view(), name="mark-read"),
    # Reactions
    path("chats/<str:chat_id>/messages/<str:message_id>/reaction", ReactionView.as_view(), name="message-reaction"),
    # ── UI ─────────────────────────────────────────────────────────────────────
    path("chatwave/", ChatWaveView.as_view(), name="chatwave"),
    path("login/", AuthView.as_view(), name="login"),
]