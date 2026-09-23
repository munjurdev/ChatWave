from django.db.models import Max, Count, Q, Prefetch
from django.contrib.auth import get_user_model
from django.views.generic import TemplateView
User = get_user_model()
from rest_framework import viewsets, generics, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError, PermissionDenied

from .models import Chat, ChatMembership, Message, MessageRead, MessageReaction
from .serializers import (
    ChatListSerializer,
    ChatDetailSerializer,
    MessageSerializer,
    UserMeSerializer,
)
from .utils import broadcast_message


class UserMeView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserMeSerializer

    def get_object(self):
        return self.request.user


class ChatViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ChatDetailSerializer
        return ChatListSerializer

    def create(self, request, *args, **kwargs):
        return Response({"message": "Use /private or /group"}, status=405)

    def get_queryset(self):
        user = self.request.user

        # Prefetch messages and reads for optimization
        messages_prefetch = Prefetch(
            "messages",
            Message.objects.filter(is_deleted=False).select_related("sender").prefetch_related("reads")
        )

        return Chat.objects.filter(
            memberships__user=user
        ).distinct().prefetch_related(
            messages_prefetch,
            "memberships__user"
        ).annotate(
            last_time=Max("messages__created_at"),
        ).order_by("-last_time")

    def retrieve(self, request, *args, **kwargs):
        """Get chat details"""
        chat = self.get_object()
        serializer = self.get_serializer(chat, context={"request": request})
        return Response(serializer.data)

    # ================= PRIVATE CHAT =================
    @action(detail=False, methods=["post"], url_path="private")
    def private(self, request):
        other_id = request.data.get("user_id")

        if other_id == str(request.user.id):
            return Response({"error": "Cannot chat with yourself"}, status=400)

        existing = Chat.objects.filter(
            is_group=False,
            memberships__user=request.user
        ).filter(
            memberships__user_id=other_id
        ).first()

        if existing:
            serializer = ChatListSerializer(existing, context={"request": request})
            return Response(serializer.data)

        with transaction.atomic():
            chat = Chat.objects.create(is_group=False)
            ChatMembership.objects.create(chat=chat, user=request.user)
            ChatMembership.objects.create(chat=chat, user_id=other_id)

        serializer = ChatListSerializer(chat, context={"request": request})
        return Response(serializer.data, status=201)

    # ================= GROUP CHAT =================
    @action(detail=False, methods=["post"], url_path="group")
    def group(self, request):
        user = request.user
        name = request.data.get("name", f"Group - {user.email}")

        with transaction.atomic():
            chat = Chat.objects.create(is_group=True, name=name)
            ChatMembership.objects.create(chat=chat, user=user)

        serializer = ChatListSerializer(chat, context={"request": request})
        return Response(serializer.data, status=201)

    # ================= ADD MEMBER =================
    @action(detail=True, methods=["post"], url_path="add-member")
    def add_member(self, request, pk=None):
        chat = self.get_object()
        user_id = request.data.get("user_id")

        if not user_id:
            return Response({"error": "user_id required"}, status=400)

        membership, created = ChatMembership.objects.get_or_create(chat=chat, user_id=user_id)
        return Response(
            {"message": "Member added" if created else "Already a member"},
            status=201 if created else 200
        )

    # ================= REMOVE MEMBER =================
    @action(detail=True, methods=["post"], url_path="remove-member")
    def remove_member(self, request, pk=None):
        chat = self.get_object()
        user_id = request.data.get("user_id")

        if not user_id:
            return Response({"error": "user_id required"}, status=400)

        deleted, _ = ChatMembership.objects.filter(chat=chat, user_id=user_id).delete()
        
        if deleted:
            return Response({"message": "Member removed"})
        return Response({"error": "Member not found"}, status=404)


class MessageListCreateView(generics.ListCreateAPIView):
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        chat_id = self.kwargs.get("chat_id")
        user = self.request.user

        messages = Message.objects.filter(
            chat_id=chat_id,
            is_deleted=False
        ).select_related("sender").prefetch_related("reads").order_by("-created_at")

        # OPTIMIZED: Single bulk operation instead of N+1 queries
        # Get IDs of messages NOT sent by this user and NOT yet read
        already_read_ids = MessageRead.objects.filter(
            message__chat_id=chat_id,
            user=user
        ).values_list("message_id", flat=True)

        unread_msgs = messages.exclude(
            sender=user
        ).exclude(
            id__in=already_read_ids
        )

        now = timezone.now()
        if unread_msgs.exists():
            MessageRead.objects.bulk_create(
                [
                    MessageRead(message=msg, user=user, read_at=now, delivered_at=now)
                    for msg in unread_msgs
                ],
                ignore_conflicts=True  # Skip if already exists (race condition safety)
            )

        return messages

    def perform_create(self, serializer):
        chat_id = self.kwargs.get("chat_id")

        if not ChatMembership.objects.filter(
            chat_id=chat_id,
            user=self.request.user
        ).exists():
            raise PermissionDenied("Not a member of this chat")

        file = self.request.FILES.get("file")
        voice = self.request.FILES.get("voice")

        # prevent both
        if file and voice:
            raise ValidationError("Cannot send both file and voice")

        # max size
        for f in [file, voice]:
            if f and f.size > 10 * 1024 * 1024:
                raise ValidationError("Max file size is 10MB")

        msg = serializer.save(
            chat_id=chat_id,
            sender=self.request.user
        )

        # Reload with sender so build_message_event has all needed fields
        msg = Message.objects.select_related("sender").get(pk=msg.pk)

        # Broadcast to WebSocket — auto real-time update for file/voice messages
        broadcast_message(msg)


class MarkAsReadView(generics.GenericAPIView):
    """Mark message(s) as read"""
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # Prefer message_id from URL kwargs (consistent with route pattern),
        # fall back to request body for backwards compatibility
        message_id = kwargs.get("message_id") or request.data.get("message_id")
        chat_id = kwargs.get("chat_id")

        # Verify membership
        if not ChatMembership.objects.filter(
            chat_id=chat_id,
            user=request.user
        ).exists():
            return Response({"error": "Not a member"}, status=403)

        if not message_id:
            return Response({"error": "message_id required"}, status=400)

        # Mark as read
        obj, created = MessageRead.objects.update_or_create(
            message_id=message_id,
            user=request.user,
            defaults={"read_at": timezone.now()}
        )

        return Response({
            "message_id": message_id,
            "read_at": obj.read_at.isoformat().replace("+00:00", "Z"),
            "is_new": created
        })


class ReactionView(generics.GenericAPIView):
    """Manage message reactions"""
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        """Add reaction to message"""
        chat_id = kwargs.get("chat_id")
        message_id = kwargs.get("message_id")
        reaction_type = request.data.get("reaction")

        # Verify membership
        if not ChatMembership.objects.filter(
            chat_id=chat_id,
            user=request.user
        ).exists():
            return Response({"error": "Not a member"}, status=403)

        # Validate reaction type
        valid_reactions = dict(MessageReaction.REACTIONS)
        if reaction_type not in valid_reactions:
            return Response(
                {"error": f"Invalid reaction. Choose from: {', '.join(valid_reactions.keys())}"},
                status=400
            )

        # Add reaction
        reaction, created = MessageReaction.objects.update_or_create(
            message_id=message_id,
            user=request.user,
            defaults={"reaction": reaction_type}
        )

        return Response({
            "message_id": message_id,
            "reaction": reaction_type,
            "emoji": valid_reactions[reaction_type],
            "is_new": created
        }, status=201 if created else 200)

    def delete(self, request, *args, **kwargs):
        """Remove reaction from message"""
        chat_id = kwargs.get("chat_id")
        message_id = kwargs.get("message_id")
        reaction_type = request.data.get("reaction")

        # Verify membership
        if not ChatMembership.objects.filter(
            chat_id=chat_id,
            user=request.user
        ).exists():
            return Response({"error": "Not a member"}, status=403)

        # Remove reaction
        deleted, _ = MessageReaction.objects.filter(
            message_id=message_id,
            user=request.user,
            reaction=reaction_type
        ).delete()

        if deleted:
            return Response({"message": "Reaction removed"})
        return Response({"error": "Reaction not found"}, status=404)


# ── UI Views ──────────────────────────────────────────────────────────────────
class ChatWaveView(TemplateView):
    """ChatWave Web UI."""
    template_name = "chat/chatwave.html"
    permission_classes = [AllowAny]

class AuthView(TemplateView):
    """Authentication UI."""
    template_name = "chat/auth.html"
    permission_classes = [AllowAny]


class LandingPageView(TemplateView):
    """Marketing landing page (site root)."""
    template_name = "chat/landing.html"
    permission_classes = [AllowAny]


class InfoPageView(TemplateView):
    """Standalone info pages: news / features / careers / help."""
    template_name = "chat/info.html"
    permission_classes = [AllowAny]

    SECTIONS = {"news", "features", "careers", "help"}

    SECTION_META = {
        "news": {
            "title": "Latest Updates — ChatWave",
            "description": "Product releases, security improvements and platform upgrades — everything shipping on ChatWave.",
        },
        "features": {
            "title": "Platform Features — ChatWave",
            "description": "Real-time messaging, group chats, voice notes, reactions and themes — everything you need to stay connected.",
        },
        "careers": {
            "title": "Careers — ChatWave",
            "description": "Help us build the future of real-time messaging. Remote-first, globally distributed.",
        },
        "help": {
            "title": "Help Center — ChatWave",
            "description": "Guides, documentation and direct support — find what you need in minutes.",
        },
    }

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        section = kwargs.get("section", "news")
        if section not in self.SECTIONS:
            section = "news"
        meta = self.SECTION_META[section]
        ctx["section"] = section
        ctx["page_title"] = meta["title"]
        ctx["page_description"] = meta["description"]
        return ctx

class UserListView(generics.ListAPIView):
    """List all registered users to start a new chat"""
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return User.objects.filter(is_active=True).exclude(id=self.request.user.id).order_by("email")
        
    def list(self, request, *args, **kwargs):
        users = self.get_queryset()
        data = [
            {
                "id": str(u.id),
                "email": u.email,
                "full_name": u.full_name or u.email,
                "display_name": u.full_name or u.email.split("@")[0],
                "is_online": getattr(u, 'is_online', False),
                "avatar": request.build_absolute_uri(u.avatar.url) if u.avatar else None,
            }
            for u in users
        ]
        return Response(data)
