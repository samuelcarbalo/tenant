from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from authentication.models import User


class JWTAuthMiddleware(BaseMiddleware):
    """Autentica conexiones WebSocket mediante JWT en query string."""

    async def __call__(self, scope, receive, send):
        scope["user"] = await self.get_user(scope)
        return await super().__call__(scope, receive, send)

    @database_sync_to_async
    def get_user(self, scope):
        query_string = scope.get("query_string", b"").decode()
        params = parse_qs(query_string)
        token_list = params.get("token", [])
        if not token_list:
            return AnonymousUser()

        try:
            access_token = AccessToken(token_list[0])
            user_id = access_token["user_id"]
            return User.objects.get(id=user_id)
        except (InvalidToken, TokenError, User.DoesNotExist, KeyError):
            return AnonymousUser()


def JWTAuthMiddlewareStack(inner):
    return JWTAuthMiddleware(inner)
