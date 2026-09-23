import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone

from .models import ChatMembership, Message, UserStatus, MessageRead, MessageReaction
from .utils import build_message_event

logger = logging.getLogger(__name__)


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.chat_id = self.scope["url_route"]["kwargs"]["chat_id"]
        self.group = f"chat_{self.chat_id}"
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            return await self.close()

        if not await self.is_member(self.user.id):
            return await self.close()

        await self.set_online(self.user.id)

        # Broadcast online status to all chats
        await self.broadcast_user_status(self.user.id, True)

        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        # Guard: user/group may not be set if connect() was rejected early
        if hasattr(self, "user") and self.user.is_authenticated:
            await self.set_offline(self.user.id)
            await self.broadcast_user_status(self.user.id, False)
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive(self, text_data):
        # ── Top-level guard: catch BaseException so CancelledError is also handled ──
        try:
            await self._dispatch(text_data)
        except Exception as exc:
            logger.exception("ChatConsumer.receive() error: %s", exc)
            print(f"[CHAT ERROR] receive() exception: {type(exc).__name__}: {exc}")
            try:
                await self.send(json.dumps({"error": "Server error", "detail": str(exc)}))
            except Exception:
                pass
        except BaseException as exc:
            # CancelledError / KeyboardInterrupt etc — log then re-raise
            print(f"[CHAT FATAL] receive() BaseException: {type(exc).__name__}: {exc}")
            logger.critical("ChatConsumer.receive() BaseException: %s", exc)
            raise

    async def _dispatch(self, text_data):
        """Inner dispatch — called from receive()'s try/except."""
        print(f"[CHAT DEBUG] _dispatch called: {text_data[:80]}")
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(json.dumps({"error": "Invalid JSON"}))
            return

        msg_type = data.get("type")
        logger.debug("ChatConsumer received type=%r chat=%s user=%s", msg_type, self.chat_id, self.user.id)

        # ── Typing indicator ──────────────────────────────────────────────────────
        if msg_type == "typing":
            # Safer way to get a display name
            display_name = getattr(self.user, "email", "Someone")
            try:
                if hasattr(self.user, "profile") and self.user.profile.full_name:
                    display_name = self.user.profile.full_name
            except Exception:
                pass

            await self.group_send({
                "type": "typing",
                "user_id": str(self.user.id),
                "full_name": display_name,
                "is_typing": data.get("is_typing", False),
            })
            return

        # ── Read receipt ──────────────────────────────────────────────────────────
        if msg_type == "read":
            message_id = data.get("message_id")
            if not message_id:
                await self.send(json.dumps({"error": "message_id required"}))
                return
            await self.mark_as_read(message_id, self.user.id)
            await self.group_send({
                "type": "message_read",
                "message_id": message_id,
                "user_id": str(self.user.id),
                "read_at": timezone.now().isoformat().replace("+00:00", "Z"),
            })
            # Also notify the sidebar to clear the unread badge
            await self.channel_layer.group_send(
                f"user_chats_{self.user.id}",
                {
                    "type": "unread_cleared",
                    "chat_id": str(self.chat_id),
                }
            )
            return

        # ── Delivery receipt ──────────────────────────────────────────────────────
        if msg_type == "delivered":
            message_id = data.get("message_id")
            if message_id:
                await self.mark_as_delivered(message_id, self.user.id)
                await self.group_send({
                    "type": "message_delivered",
                    "message_id": message_id,
                    "user_id": str(self.user.id),
                })
            return

        # ── Add reaction ──────────────────────────────────────────────────────────
        if msg_type == "add_reaction":
            message_id = data.get("message_id")
            reaction_type = data.get("reaction")
            
            # DB Helper will handle the logic
            result = await self.add_reaction(message_id, self.user.id, reaction_type)
            
            if result:
                # If it was a REPLACE, we first tell everyone to remove the old one
                if result.get("old_emoji"):
                    await self.group_send({
                        "type": "reaction_removed",
                        "message_id": message_id,
                        "user_id": str(self.user.id),
                        "reaction": "old", 
                        "emoji": result["old_emoji"],
                    })

                if result["action"] == "removed":
                    await self.group_send({
                        "type": "reaction_removed",
                        "message_id": message_id,
                        "user_id": str(self.user.id),
                        "reaction": reaction_type,
                        "emoji": result["emoji"],
                    })
                else:
                    await self.group_send({
                        "type": "reaction_added",
                        "message_id": message_id,
                        "user_id": str(self.user.id),
                        "reaction": reaction_type,
                        "emoji": result["emoji"],
                    })
            else:
                await self.send(json.dumps({"error": "Invalid reaction type"}))
            return

        # ── Remove reaction ───────────────────────────────────────────────────────
        if msg_type == "remove_reaction":
            message_id = data.get("message_id")
            reaction_type = data.get("reaction")
            await self.remove_reaction(message_id, self.user.id, reaction_type)
            await self.group_send({
                "type": "reaction_removed",
                "message_id": message_id,
                "user_id": str(self.user.id),
                "reaction": reaction_type,
                "emoji": dict(MessageReaction.REACTIONS).get(reaction_type),
            })
            return

        # ── Send message (default) ────────────────────────────────────────────────
        if msg_type in ("message", None):
            event = await self.create_and_build_message(self.user.id, data)
            logger.debug("Message created: id=%s", event.get("id"))

            # Broadcast to all members in the chat room
            await self.group_send(event)

            # Notify chat-list sidebar consumers for ALL members
            chat_members = await self.get_chat_member_ids(self.chat_id)
            for member_id in chat_members:
                await self.channel_layer.group_send(
                    f"user_chats_{member_id}",
                    {
                        "type": "new_message_in_chat",
                        "chat_id": str(self.chat_id),
                        "message": event,
                    },
                )
            return

        # ── Edit message ──────────────────────────────────────────────────────────
        if msg_type == "edit_message":
            message_id = data.get("message_id")
            new_content = data.get("content")
            if not message_id or new_content is None:
                await self.send(json.dumps({"error": "message_id and content required"}))
                return
            
            success = await self.edit_message(message_id, self.user.id, new_content)
            if success:
                await self.group_send({
                    "type": "message_edited",
                    "message_id": message_id,
                    "content": new_content,
                    "edited_at": timezone.now().isoformat().replace("+00:00", "Z"),
                })
            else:
                await self.send(json.dumps({"error": "Edit failed (unauthorized or not found)"}))
            return

        # ── Delete message ────────────────────────────────────────────────────────
        if msg_type == "delete_message":
            message_id = data.get("message_id")
            if not message_id:
                await self.send(json.dumps({"error": "message_id required"}))
                return
            
            success = await self.delete_message(message_id, self.user.id)
            if success:
                await self.group_send({
                    "type": "message_deleted",
                    "message_id": message_id,
                })
            else:
                await self.send(json.dumps({"error": "Delete failed (unauthorized or not found)"}))
            return

        # ── Unknown type ──────────────────────────────────────────────────────────
        await self.send(json.dumps({"error": f"Unknown message type: {msg_type}"}))

    # ── Channel-layer event handlers ──────────────────────────────────────────────
    # These are dispatched ASYNCHRONOUSLY by Django Channels after group_send().
    # They run OUTSIDE receive()'s try/except, so they must be guarded separately.

    async def message(self, event):
        try:
            await self.send(json.dumps(event))
            # If we are the recipient (not the sender), mark as delivered and notify sender
            sender_id = event.get("sender", {}).get("id")
            if sender_id and str(sender_id) != str(self.user.id):
                message_id = event.get("id")
                if message_id:
                    await self.mark_as_delivered(message_id, self.user.id)
                    await self.group_send({
                        "type": "message_delivered",
                        "message_id": message_id,
                        "user_id": str(self.user.id),
                    })
        except Exception as exc:
            logger.exception("ChatConsumer.message() handler error: %s", exc)
        except BaseException as exc:
            logger.critical("ChatConsumer.message() BaseException: %s", exc)

    async def typing(self, event):
        try:
            await self.send(json.dumps(event))
        except BaseException as exc:
            print(f"[CHAT FATAL] typing() BaseException: {type(exc).__name__}: {exc}")

    async def message_read(self, event):
        try:
            await self.send(json.dumps(event))
        except BaseException as exc:
            print(f"[CHAT FATAL] message_read() BaseException: {type(exc).__name__}: {exc}")

    async def reaction_added(self, event):
        try:
            await self.send(json.dumps(event))
        except BaseException as exc:
            print(f"[CHAT FATAL] reaction_added() BaseException: {type(exc).__name__}: {exc}")

    async def reaction_removed(self, event):
        try:
            await self.send(json.dumps(event))
        except BaseException as exc:
            print(f"[CHAT FATAL] reaction_removed() BaseException: {type(exc).__name__}: {exc}")

    async def message_edited(self, event):
        try:
            await self.send(json.dumps(event))
        except BaseException as exc:
            print(f"[CHAT FATAL] message_edited() BaseException: {type(exc).__name__}: {exc}")

    async def message_deleted(self, event):
        try:
            await self.send(json.dumps(event))
        except BaseException as exc:
            print(f"[CHAT FATAL] message_deleted() BaseException: {type(exc).__name__}: {exc}")

    async def message_delivered(self, event):
        try:
            await self.send(json.dumps(event))
        except BaseException as exc:
            print(f"[CHAT FATAL] message_delivered() BaseException: {type(exc).__name__}: {exc}")

    async def user_status(self, event):
        try:
            await self.send(json.dumps(event))
        except BaseException as exc:
            print(f"[CHAT FATAL] user_status() BaseException: {type(exc).__name__}: {exc}")

    async def group_send(self, event):
        await self.channel_layer.group_send(self.group, event)

    # ── DB helpers ────────────────────────────────────────────────────────────────

    @database_sync_to_async
    def is_member(self, user_id):
        return ChatMembership.objects.filter(chat_id=self.chat_id, user_id=user_id).exists()

    @database_sync_to_async
    def create_and_build_message(self, user_id, data):
        """
        Create the message AND build the broadcast event dict in a single
        @database_sync_to_async block so select_related works and there are
        no cross-thread lazy-load issues.
        """
        msg = Message.objects.create(
            chat_id=self.chat_id,
            sender_id=user_id,
            content=data.get("content"),
            file=data.get("file") if isinstance(data.get("file"), str) else None,
            voice=data.get("voice") if isinstance(data.get("voice"), str) else None,
        )
        # Reload with sender eagerly so build_message_event has all fields
        msg = Message.objects.select_related("sender").get(pk=msg.pk)
        return build_message_event(msg)

    @database_sync_to_async
    def mark_as_read(self, message_id, user_id):
        """Mark message as read by user."""
        MessageRead.objects.update_or_create(
            message_id=message_id,
            user_id=user_id,
            defaults={"read_at": timezone.now()},
        )

    @database_sync_to_async
    def mark_as_delivered(self, message_id, user_id):
        """Mark message as delivered to user."""
        # Only set delivered_at if it's currently null
        obj, created = MessageRead.objects.get_or_create(
            message_id=message_id,
            user_id=user_id
        )
        if not obj.delivered_at:
            obj.delivered_at = timezone.now()
            obj.save()

    @database_sync_to_async
    def add_reaction(self, message_id, user_id, reaction_type):
        """Add, toggle, or replace a reaction."""
        try:
            msg = Message.objects.get(id=message_id)
            valid_reactions = dict(MessageReaction.REACTIONS)
            emoji = valid_reactions.get(reaction_type)
            if not emoji: return None

            existing = MessageReaction.objects.filter(message=msg, user_id=user_id).first()
            old_emoji = None
            if existing:
                if existing.reaction == reaction_type:
                    # Toggle OFF
                    existing.delete()
                    return {"action": "removed", "emoji": emoji}
                else:
                    # REPLACE logic
                    old_emoji = valid_reactions.get(existing.reaction)
                    existing.delete()
            
            # Add NEW or REPLACED
            MessageReaction.objects.create(message=msg, user_id=user_id, reaction=reaction_type)
            return {"action": "added", "emoji": emoji, "old_emoji": old_emoji}
        except Message.DoesNotExist:
            return None

    @database_sync_to_async
    def remove_reaction(self, message_id, user_id, reaction_type):
        """Remove reaction from message."""
        MessageReaction.objects.filter(
            message_id=message_id,
            user_id=user_id,
            reaction=reaction_type,
        ).delete()

    @database_sync_to_async
    def edit_message(self, message_id, user_id, new_content):
        """Edit message content if user is sender."""
        try:
            msg = Message.objects.get(id=message_id, sender_id=user_id)
            msg.content = new_content
            msg.is_edited = True
            msg.save()
            return True
        except Message.DoesNotExist:
            return False

    @database_sync_to_async
    def delete_message(self, message_id, user_id):
        """Soft delete message if user is sender."""
        try:
            msg = Message.objects.get(id=message_id, sender_id=user_id)
            msg.is_deleted = True
            msg.save()
            return True
        except Message.DoesNotExist:
            return False

    @database_sync_to_async
    def set_online(self, user_id):
        UserStatus.objects.update_or_create(user_id=user_id, defaults={"is_online": True})

    @database_sync_to_async
    def set_offline(self, user_id):
        UserStatus.objects.update_or_create(
            user_id=user_id,
            defaults={"is_online": False, "last_seen": timezone.now()},
        )

    async def broadcast_user_status(self, user_id, is_online):
        """Broadcast user online/offline status to all their chat rooms and sidebar groups."""
        chats = await self.get_user_chats(user_id)
        last_seen = timezone.now().isoformat().replace("+00:00", "Z") if not is_online else None
        
        # Notify specific chat rooms (for active headers)
        for chat_id in chats:
            await self.channel_layer.group_send(
                f"chat_{chat_id}",
                {
                    "type": "user_status",
                    "user_id": str(user_id),
                    "is_online": is_online,
                    "last_seen": last_seen,
                },
            )
            
            # Notify ALL members of those chats in their sidebar groups
            member_ids = await self.get_chat_member_ids(chat_id)
            for m_id in member_ids:
                if str(m_id) != str(user_id):
                    await self.channel_layer.group_send(
                        f"user_chats_{m_id}",
                        {
                            "type": "user_status",
                            "user_id": str(user_id),
                            "is_online": is_online,
                            "last_seen": last_seen,
                        }
                    )

    @database_sync_to_async
    def get_user_chats(self, user_id):
        """Return list of chat IDs this user belongs to."""
        return list(ChatMembership.objects.filter(user_id=user_id).values_list("chat_id", flat=True))

    @database_sync_to_async
    def get_chat_member_ids(self, chat_id):
        """Return list of user IDs belonging to this chat."""
        return list(ChatMembership.objects.filter(chat_id=chat_id).values_list("user_id", flat=True))


# ═══════════════════════════════════════════════════════════════════════════════
class ChatListConsumer(AsyncWebsocketConsumer):
    """Real-time chat list updates consumer (sidebar / unread badges)."""

    async def connect(self):
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            return await self.close()

        await self.set_online(self.user.id)
        # Mark all pending messages as delivered upon login
        await self.mark_all_pending_as_delivered(self.user.id)
        await self.broadcast_user_status(self.user.id, True)

        self.group = f"user_chats_{self.user.id}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "user") and self.user.is_authenticated:
            await self.set_offline(self.user.id)
            await self.broadcast_user_status(self.user.id, False)
        # Guard: group may not be set if connect() was rejected early
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def user_status(self, event):
        """Handle user status changes (online/offline) for sidebar."""
        try:
            await self.send(json.dumps(event))
        except Exception as exc:
            logger.exception("ChatListConsumer.user_status() error: %s", exc)

    async def unread_cleared(self, event):
        """Notify sidebar to clear unread count for a chat."""
        try:
            await self.send(json.dumps(event))
        except Exception as exc:
            logger.exception("ChatListConsumer.unread_cleared() error: %s", exc)

    async def chat_updated(self, event):
        """Broadcast chat list update."""
        try:
            await self.send(json.dumps({
                "type": "chat_updated",
                "chat_id": event["chat_id"],
                "last_message": event["last_message"],
                "unread_count": event["unread_count"],
                "updated_at": event["updated_at"],
            }))
        except Exception as exc:
            logger.exception("ChatListConsumer.chat_updated() error: %s", exc)

    async def new_message_in_chat(self, event):
        """Broadcast new message to chat list consumers."""
        try:
            await self.send(json.dumps(event))
            # If we are the recipient, mark as delivered
            message_id = event.get("message", {}).get("id")
            sender_id = event.get("message", {}).get("sender", {}).get("id")
            if message_id and sender_id and str(sender_id) != str(self.user.id):
                chat_id = event.get("chat_id")
                await self.mark_as_delivered(message_id, self.user.id)
                await self.channel_layer.group_send(
                    f"chat_{chat_id}",
                    {
                        "type": "message_delivered",
                        "message_id": message_id,
                        "user_id": str(self.user.id),
                    }
                )
        except Exception as exc:
            logger.exception("ChatListConsumer.new_message_in_chat() error: %s", exc)

    @database_sync_to_async
    def set_online(self, user_id):
        from .models import UserStatus
        UserStatus.objects.update_or_create(user_id=user_id, defaults={"is_online": True})

    @database_sync_to_async
    def set_offline(self, user_id):
        from .models import UserStatus
        from django.utils import timezone
        UserStatus.objects.update_or_create(
            user_id=user_id,
            defaults={"is_online": False, "last_seen": timezone.now()},
        )

    @database_sync_to_async
    def mark_all_pending_as_delivered(self, user_id):
        """Mark all undelivered messages for this user as delivered."""
        from .models import Message, MessageRead, ChatMembership
        from django.utils import timezone
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        
        user_chats = list(ChatMembership.objects.filter(user_id=user_id).values_list("chat_id", flat=True))
        pending_messages = Message.objects.filter(
            chat_id__in=user_chats
        ).exclude(sender_id=user_id)
        
        now = timezone.now()
        layer = get_channel_layer()
        for msg in pending_messages:
            obj, created = MessageRead.objects.get_or_create(message=msg, user_id=user_id)
            if not obj.delivered_at:
                obj.delivered_at = now
                obj.save()
                async_to_sync(layer.group_send)(f"chat_{msg.chat_id}", {
                    "type": "message_delivered",
                    "message_id": str(msg.id),
                    "user_id": str(user_id),
                })

    async def broadcast_user_status(self, user_id, is_online):
        """Broadcast user online/offline status to all their chat rooms and sidebar groups."""
        chats = await self.get_user_chats(user_id)
        from django.utils import timezone
        last_seen = timezone.now().isoformat().replace("+00:00", "Z") if not is_online else None
        
        # Notify specific chat rooms (for active headers)
        for chat_id in chats:
            await self.channel_layer.group_send(
                f"chat_{chat_id}",
                {
                    "type": "user_status",
                    "user_id": str(user_id),
                    "is_online": is_online,
                    "last_seen": last_seen,
                },
            )
            
            # Notify ALL members of those chats in their sidebar groups
            member_ids = await self.get_chat_member_ids(chat_id)
            for m_id in member_ids:
                if str(m_id) != str(user_id):
                    await self.channel_layer.group_send(
                        f"user_chats_{m_id}",
                        {
                            "type": "user_status",
                            "user_id": str(user_id),
                            "is_online": is_online,
                            "last_seen": last_seen,
                        }
                    )

    @database_sync_to_async
    def get_user_chats(self, user_id):
        """Return list of chat IDs this user belongs to."""
        from .models import ChatMembership
        return list(ChatMembership.objects.filter(user_id=user_id).values_list("chat_id", flat=True))

    @database_sync_to_async
    def get_chat_member_ids(self, chat_id):
        """Return list of user IDs belonging to this chat."""
        from .models import ChatMembership
        return list(ChatMembership.objects.filter(chat_id=chat_id).values_list("user_id", flat=True))

    @database_sync_to_async
    def mark_as_delivered(self, message_id, user_id):
        """Mark message as delivered to user."""
        from .models import MessageRead
        from django.utils import timezone
        obj, created = MessageRead.objects.get_or_create(
            message_id=message_id,
            user_id=user_id
        )
        if not obj.delivered_at:
            obj.delivered_at = timezone.now()
            obj.save()