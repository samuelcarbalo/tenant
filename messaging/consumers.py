import json

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone

from .services import (
    mark_conversation_as_read,
    send_message,
    user_can_access_conversation,
)


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer para mensajería en tiempo real.

    URL: ws/messaging/conversations/<conversation_id>/?token=<jwt>
    Eventos entrantes: message.send, typing.start, typing.stop, read.mark
    Eventos salientes: message.new, typing, read.update, error
    """

    async def connect(self):
        self.conversation_id = self.scope["url_route"]["kwargs"]["conversation_id"]
        self.user = self.scope.get("user")

        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        has_access = await self._check_access()
        if not has_access:
            await self.close(code=4003)
            return

        self.room_group_name = f"chat_{self.conversation_id}"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "presence.update",
                "user_id": str(self.user.id),
                "status": "online",
            },
        )

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(
                self.room_group_name, self.channel_name
            )
            if self.user and self.user.is_authenticated:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "presence.update",
                        "user_id": str(self.user.id),
                        "status": "offline",
                    },
                )

    async def receive_json(self, content, **kwargs):
        event_type = content.get("type")

        if event_type == "message.send":
            await self._handle_send_message(content)
        elif event_type == "typing.start":
            await self._handle_typing("start")
        elif event_type == "typing.stop":
            await self._handle_typing("stop")
        elif event_type == "read.mark":
            await self._handle_mark_read()

    async def _handle_send_message(self, content):
        body = content.get("body", "").strip()
        if not body:
            await self.send_json({"type": "error", "message": "Mensaje vacío."})
            return

        try:
            message_data = await self._create_message(body)
        except (PermissionError, ValueError) as e:
            await self.send_json({"type": "error", "message": str(e)})
            return

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat.message",
                "message": message_data,
            },
        )

    async def _handle_typing(self, action):
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat.typing",
                "user_id": str(self.user.id),
                "username": self.user.username,
                "action": action,
            },
        )

    async def _handle_mark_read(self):
        await self._mark_read()
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat.read",
                "user_id": str(self.user.id),
                "read_at": timezone.now().isoformat(),
            },
        )

    async def chat_message(self, event):
        await self.send_json({"type": "message.new", "message": event["message"]})

    async def chat_typing(self, event):
        if event["user_id"] != str(self.user.id):
            await self.send_json(
                {
                    "type": "typing",
                    "user_id": event["user_id"],
                    "username": event["username"],
                    "action": event["action"],
                }
            )

    async def chat_read(self, event):
        await self.send_json({"type": "read.update", **event})

    async def presence_update(self, event):
        if event["user_id"] != str(self.user.id):
            await self.send_json({"type": "presence", **event})

    @database_sync_to_async
    def _check_access(self):
        from .models import Conversation

        try:
            conversation = Conversation.objects.get(pk=self.conversation_id)
            return user_can_access_conversation(self.user, conversation)
        except Conversation.DoesNotExist:
            return False

    @database_sync_to_async
    def _create_message(self, body):
        from .models import Conversation
        from .serializers import MessageSerializer

        conversation = Conversation.objects.get(pk=self.conversation_id)
        message = send_message(
            conversation=conversation,
            sender=self.user,
            body=body,
        )
        return MessageSerializer(message, context={"request": type("R", (), {"user": self.user})()}).data

    @database_sync_to_async
    def _mark_read(self):
        from .models import Conversation

        conversation = Conversation.objects.get(pk=self.conversation_id)
        mark_conversation_as_read(conversation, self.user)
