
from django.urls import path
from . import consumers

websocket_urlpatterns = [
    # 📋 Chat list WebSocket (REALTIME LIST UPDATES)
    path("list/", consumers.ChatListConsumer.as_asgi(), name="ws-chat-list"),
    # 💬 Chat room WebSocket (REALTIME MESSAGES)
    path("<str:chat_id>/", consumers.ChatConsumer.as_asgi(), name="ws-chat"),
]
