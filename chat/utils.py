"""
chat/utils.py
─────────────
Shared helpers used by both the REST views (sync) and the WebSocket
consumers (async) so that the message-event format is always consistent.
"""
import logging

logger = logging.getLogger(__name__)


def build_message_event(msg) -> dict:
    """
    Build the dict that is broadcast over WebSocket for a given Message instance.
    `msg` must have its `sender` relation already loaded (use select_related).
    """
    sender = msg.sender

    # Safely resolve avatar URL — FileField raises ValueError when no file is set
    avatar = None
    if getattr(sender, "avatar", None) and sender.avatar:
        try:
            avatar = sender.avatar.url
        except (ValueError, AttributeError):
            avatar = None

    return {
        "type": "message",
        "id": str(msg.id),
        "chat": str(msg.chat_id),
        "message_type": msg.type,
        "sender": {
            "id": str(sender.id),
            "email": sender.email,
            "role": getattr(sender, "role", None),
            "full_name": getattr(sender, "full_name", "") or sender.email,
            "avatar": avatar,
        },
        "content": msg.content,
        "file": msg.file.url if msg.file else None,
        "voice": msg.voice.url if msg.voice else None,
        "created_at": msg.created_at.isoformat().replace("+00:00", "Z"),
        "is_edited": msg.is_edited,
        "is_deleted": msg.is_deleted,
        "delivered_count": msg.reads.filter(delivered_at__isnull=False).count(),
        "read_count": msg.reads.filter(read_at__isnull=False).count(),
    }


def broadcast_message(msg) -> None:
    """
    Synchronous wrapper: build the event and push it to the channel layer
    so all connected WebSocket clients receive the message in real-time.

    Safe to call from Django REST views (sync context).
    Falls back silently if the channel layer is not configured.
    """
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync

    channel_layer = get_channel_layer()
    if not channel_layer:
        logger.warning("broadcast_message: no channel layer configured — skipping WS broadcast")
        return

    event = build_message_event(msg)
    sender_id = str(msg.sender_id)
    chat_id = str(msg.chat_id)

    try:
        # 1. Broadcast to all members currently in the chat room
        async_to_sync(channel_layer.group_send)(f"chat_{chat_id}", event)

        # 2. Notify chat-list consumers (sidebar / unread-badge updates)
        async_to_sync(channel_layer.group_send)(
            f"user_chats_{sender_id}",
            {
                "type": "new_message_in_chat",
                "chat_id": chat_id,
                "message": event,
            },
        )
    except Exception as exc:
        # Never let a broadcast failure break the REST response
        logger.exception("broadcast_message failed for msg=%s: %s", msg.id, exc)
