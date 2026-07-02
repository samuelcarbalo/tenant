from django.contrib import admin

from .models import Conversation, ConversationParticipant, Message, MessageReadStatus


class ParticipantInline(admin.TabularInline):
    model = ConversationParticipant
    extra = 0
    raw_id_fields = ["user"]


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    raw_id_fields = ["sender"]
    readonly_fields = ["created_at"]
    fields = ["sender", "body", "is_deleted", "created_at"]


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ["subject", "conversation_type", "organization", "last_message_at", "is_active"]
    list_filter = ["conversation_type", "is_active", "organization"]
    search_fields = ["subject"]
    raw_id_fields = ["organization", "initiated_by"]
    inlines = [ParticipantInline, MessageInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ["conversation", "sender", "body_preview", "is_deleted", "created_at"]
    list_filter = ["is_deleted", "is_edited"]
    raw_id_fields = ["conversation", "sender"]
    search_fields = ["body"]

    def body_preview(self, obj):
        return obj.body[:60]


@admin.register(MessageReadStatus)
class MessageReadStatusAdmin(admin.ModelAdmin):
    list_display = ["message", "user", "read_at"]
    raw_id_fields = ["message", "user"]
