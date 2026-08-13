from channels.generic.websocket import AsyncJsonWebsocketConsumer

from notifications.realtime import user_notifications_group


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """
    Canal en vivo para la campana de la PWA.

    URL: ws/notifications/?token=<jwt>
    Eventos salientes: notification.new
    """

    async def connect(self):
        try:
            self.user = self.scope.get("user")
            if not self.user or not getattr(self.user, "is_authenticated", False):
                await self.close(code=4001)
                return

            self.group_name = user_notifications_group(self.user.id)
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
        except Exception:
            try:
                await self.close(code=1011)
            except Exception:
                pass

    async def disconnect(self, close_code):
        try:
            if hasattr(self, "group_name") and self.channel_layer:
                await self.channel_layer.group_discard(self.group_name, self.channel_name)
        except Exception:
            pass

    async def notification_new(self, event):
        try:
            await self.send_json(
                {
                    "type": "notification.new",
                    "notification": event.get("notification") or {},
                }
            )
        except Exception:
            pass

