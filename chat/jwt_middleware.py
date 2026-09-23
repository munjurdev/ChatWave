import jwt
from urllib.parse import parse_qs
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.conf import settings
from asgiref.sync import sync_to_async


User = get_user_model()


class JWTAuthMiddleware(BaseMiddleware):
    
    async def __call__(self, scope, receive, send):
        query_string = scope.get("query_string", b"").decode()
        params = parse_qs(query_string)

        token = params.get("token", [None])[0]

        # Default: anonymous user
        scope["user"] = AnonymousUser()

        if token:
            try:
                # Validate JWT
                UntypedToken(token)

                decoded = jwt.decode(
                    token, settings.SECRET_KEY, algorithms=["HS256"]
                )
                user_id = decoded.get("user_id")

                if user_id:
                    try:
                        user = await sync_to_async(User.objects.get)(id=user_id)
                        scope["user"] = user
                    except User.DoesNotExist:
                        scope["user"] = AnonymousUser()

            except (InvalidToken, TokenError, jwt.DecodeError):
                scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    return JWTAuthMiddleware(inner)
