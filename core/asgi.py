import os
from channels.routing import ProtocolTypeRouter, URLRouter

from django.core.asgi import get_asgi_application
from django.urls import path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

django_asgi_app = get_asgi_application()

from chat.jwt_middleware import JWTAuthMiddlewareStack
from chat.routing import websocket_urlpatterns as chat_ws_patterns

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddlewareStack(
        URLRouter([
            # Chat WebSocket
            path("ws/chat/", URLRouter(chat_ws_patterns)),
        ])
    ),
})

