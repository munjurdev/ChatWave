from django.contrib import admin
from .models import (
    Chat,
    ChatMembership,
    Message,
    MessageRead,
    MessageReaction,
    UserStatus,
)


# ================= CHAT =================
@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display = ("id", "is_group", "name", "created_at")
    list_filter = ("is_group", "created_at")
    search_fields = ("id", "name")
    readonly_fields = ("id", "created_at")


# ================= MEMBERSHIP =================
@admin.register(ChatMembership)
class ChatMembershipAdmin(admin.ModelAdmin):
    list_display = ("chat", "user", "joined_at")
    list_filter = ("joined_at",)
    search_fields = ("chat__id", "user__email")
    autocomplete_fields = ("user", "chat")


# ================= MESSAGE =================
@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "chat",
        "sender",
        "type",
        "is_edited",
        "is_deleted",
        "created_at",
    )

    list_filter = ("type", "is_edited", "is_deleted", "created_at")
    search_fields = ("id", "chat__id", "sender__email", "content")

    readonly_fields = ("id", "created_at")
    autocomplete_fields = ("chat", "sender")

    ordering = ("-created_at",)


# ================= READ RECEIPTS =================
@admin.register(MessageRead)
class MessageReadAdmin(admin.ModelAdmin):
    list_display = ("message", "user", "read_at")
    list_filter = ("read_at",)
    search_fields = ("message__id", "user__email")
    autocomplete_fields = ("message", "user")


# ================= REACTIONS =================
@admin.register(MessageReaction)
class MessageReactionAdmin(admin.ModelAdmin):
    list_display = ("message", "user", "reaction")
    list_filter = ("reaction",)
    search_fields = ("message__id", "user__email")
    autocomplete_fields = ("message", "user")


# ================= USER STATUS =================
@admin.register(UserStatus)
class UserStatusAdmin(admin.ModelAdmin):
    list_display = ("user", "is_online", "last_seen")
    list_filter = ("is_online",)
    search_fields = ("user__email",)
    autocomplete_fields = ("user",)