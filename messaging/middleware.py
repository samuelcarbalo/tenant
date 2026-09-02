from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

from authentication.models import User

# Códigos de cierre WebSocket (rango reservado para aplicaciones)
WS_CLOSE_UNAUTHORIZED = 4001
WS_CLOSE_TOKEN_EXPIRED = 4003


class JWTAuthMiddleware(BaseMiddleware):
    """Autentica conexiones WebSocket mediante JWT en query string (?token=)."""

    async def __call__(self, scope, receive, send):
        scope["ws_close_code"] = None
        try:
            user, close_code = await self.resolve_user(scope)
            scope["user"] = user
            if close_code:
                scope["ws_close_code"] = close_code
        except Exception:
            scope["user"] = AnonymousUser()
            scope["ws_close_code"] = WS_CLOSE_UNAUTHORIZED

        try:
            return await super().__call__(scope, receive, send)
        except Exception:
            try:
                await send(
                    {
                        "type": "websocket.close",
                        "code": scope.get("ws_close_code") or WS_CLOSE_UNAUTHORIZED,
                    }
                )
            except Exception:
                pass

    @database_sync_to_async
    def resolve_user(self, scope):
        try:
            query_string = scope.get("query_string", b"") or b""
            if isinstance(query_string, bytes):
                query_string = query_string.decode("utf-8", errors="ignore")
            params = parse_qs(query_string)
            token_list = params.get("token", [])
            raw = (token_list[0] if token_list else "").strip()
            if not raw:
                return AnonymousUser(), WS_CLOSE_UNAUTHORIZED

            try:
                access_token = AccessToken(raw)
            except TokenError as exc:
                message = str(exc).lower()
                if "expired" in message:
                    return AnonymousUser(), WS_CLOSE_TOKEN_EXPIRED
                return AnonymousUser(), WS_CLOSE_UNAUTHORIZED
            except InvalidToken:
                return AnonymousUser(), WS_CLOSE_UNAUTHORIZED

            user_id = access_token.get("user_id")
            if not user_id:
                return AnonymousUser(), WS_CLOSE_UNAUTHORIZED

            return User.objects.get(id=user_id), None
        except User.DoesNotExist:
            return AnonymousUser(), WS_CLOSE_UNAUTHORIZED
        except (KeyError, ValueError, TypeError):
            return AnonymousUser(), WS_CLOSE_UNAUTHORIZED
        except Exception:
            return AnonymousUser(), WS_CLOSE_UNAUTHORIZED


def JWTAuthMiddlewareStack(inner):
    return JWTAuthMiddleware(inner)
