from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

from authentication.models import User


class JWTAuthMiddleware(BaseMiddleware):
    """Autentica conexiones WebSocket mediante JWT en query string.

    Nunca lanza: token ausente, expirado o corrupto → AnonymousUser
    (el consumer cierra con 4001).
    """

    async def __call__(self, scope, receive, send):
        try:
            scope["user"] = await self.get_user(scope)
        except Exception:
            scope["user"] = AnonymousUser()
        try:
            return await super().__call__(scope, receive, send)
        except Exception:
            # Evita tumbar el proceso ASGI por un handshake WS fallido
            try:
                await send({"type": "websocket.close", "code": 4401})
            except Exception:
                pass

    @database_sync_to_async
    def get_user(self, scope):
        try:
            query_string = scope.get("query_string", b"") or b""
            if isinstance(query_string, bytes):
                query_string = query_string.decode("utf-8", errors="ignore")
            params = parse_qs(query_string)
            token_list = params.get("token", [])
            raw = (token_list[0] if token_list else "").strip()
            if not raw:
                return AnonymousUser()

            access_token = AccessToken(raw)
            user_id = access_token.get("user_id")
            if not user_id:
                return AnonymousUser()
            return User.objects.get(id=user_id)
        except (InvalidToken, TokenError, User.DoesNotExist, KeyError, ValueError, TypeError):
            return AnonymousUser()
        except Exception:
            return AnonymousUser()


def JWTAuthMiddlewareStack(inner):
    return JWTAuthMiddleware(inner)
