from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db.models import Count
from .models import Chat, Message, MessageRead, MessageReaction, ChatMembership

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    avatar = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    is_online = serializers.SerializerMethodField()
    last_seen = serializers.SerializerMethodField()
    is_blocked = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "display_name", "role", "avatar", "is_online", "last_seen", "is_blocked"]

    def get_display_name(self, obj):
        return obj.full_name or obj.email

    def get_is_blocked(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        from accounts.models import UserBlock
        return UserBlock.objects.filter(blocked_by=request.user, blocked_user=obj, is_deleted=False).exists()

    def get_is_online(self, obj):
        try:
            return obj.status.is_online
        except:
            return False

    def get_last_seen(self, obj):
        try:
            if obj.status.last_seen:
                return obj.status.last_seen.isoformat().replace("+00:00", "Z")
            return None
        except:
            return None

    def get_avatar(self, obj):
        if obj.avatar:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.avatar.url)
            return obj.avatar.url
        return None




class UserMeSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "full_name", "avatar"]
        read_only_fields = ["id", "email"]

    def to_representation(self, instance):
        # Use the standard UserSerializer for output to include absolute URIs for avatars
        return UserSerializer(instance, context=self.context).data


class MessageReadSerializer(serializers.ModelSerializer):
    user_id = serializers.CharField(source='user.id', read_only=True)

    class Meta:
        model = MessageRead
        fields = ["user_id", "delivered_at", "read_at"]


class MessageReactionSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = MessageReaction
        fields = ["id", "user", "reaction"]


class MessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    reads = MessageReadSerializer(many=True, read_only=True)
    reactions = serializers.SerializerMethodField()
    read_count = serializers.SerializerMethodField()
    delivered_count = serializers.SerializerMethodField()
    
    # These fields are set dynamically or are optional, so they shouldn't block validation
    chat = serializers.CharField(read_only=True)
    content = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    file = serializers.FileField(required=False, allow_null=True)
    voice = serializers.FileField(required=False, allow_null=True)

    class Meta:
        model = Message
        fields = [
            "id",
            "chat",
            "sender",
            "content",
            "type",
            "file",
            "voice",
            "created_at",
            "is_edited",
            "is_deleted",
            "reads",
            "read_count",
            "delivered_count",
            "reactions",
        ]

    def get_delivered_count(self, obj):
        return obj.reads.filter(delivered_at__isnull=False).count()

    def get_read_count(self, obj):
        return obj.reads.count()

    def get_reactions(self, obj):
        """Group reactions by emoji with user list"""
        reactions_qs = obj.reactions.select_related("user").all()
        reaction_groups = {}
        
        for reaction in reactions_qs:
            emoji = reaction.get_reaction_display()
            if emoji not in reaction_groups:
                reaction_groups[emoji] = {
                    "emoji": emoji,
                    "type": reaction.reaction,
                    "count": 0,
                    "users": []
                }
            reaction_groups[emoji]["count"] += 1
            reaction_groups[emoji]["users"].append({
                "id": str(reaction.user.id),
                "email": reaction.user.email,
                "full_name": getattr(reaction.user, "full_name", "") or reaction.user.email,
            })
        
        return list(reaction_groups.values())


class ChatDetailSerializer(serializers.ModelSerializer):
    members = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    is_member = serializers.SerializerMethodField()

    class Meta:
        model = Chat
        fields = ["id", "is_group", "name", "created_at", "members", "last_message", "unread_count", "is_member"]

    def get_members(self, obj):
        members = obj.memberships.select_related("user").all()
        return [
            {
                **UserSerializer(m.user, context=self.context).data,
                "joined_at": m.joined_at.isoformat().replace("+00:00", "Z"),
            }
            for m in members
        ]

    def get_last_message(self, obj):
        msg = obj.messages.filter(is_deleted=False).first()
        if not msg:
            return None
        return {
            "id": str(msg.id),
            "sender": {
                "id": str(msg.sender.id),
                "email": msg.sender.email,
                "full_name": getattr(msg.sender, "full_name", "") or msg.sender.email,
            },
            "content": msg.content,
            "type": msg.type,
            "created_at": msg.created_at.isoformat().replace("+00:00", "Z"),
            "read_by_count": msg.reads.count(),
        }

    def get_unread_count(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return 0
        from .models import MessageRead
        total_incoming = obj.messages.filter(is_deleted=False).exclude(sender=request.user).count()
        read_incoming = MessageRead.objects.filter(message__chat=obj, user=request.user, read_at__isnull=False).count()
        return max(0, total_incoming - read_incoming)

    def get_is_member(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return ChatMembership.objects.filter(chat=obj, user=request.user).exists()


class ChatListSerializer(serializers.ModelSerializer):
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    other_member = serializers.SerializerMethodField()
    is_blocked = serializers.SerializerMethodField()

    class Meta:
        model = Chat
        fields = ["id", "is_group", "name", "last_message", "unread_count", "other_member", "created_at", "is_blocked"]

    def get_is_blocked(self, obj):
        if obj.is_group:
            return False
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        other = obj.memberships.select_related("user").exclude(user=request.user).first()
        if not other:
            return False
        from accounts.models import UserBlock
        return UserBlock.objects.filter(blocked_by=request.user, blocked_user=other.user, is_deleted=False).exists()

    def get_last_message(self, obj):
        msg = obj.messages.filter(is_deleted=False).first()
        if not msg:
            return None
        return {
            "id": str(msg.id),
            "sender": {
                "id": str(msg.sender.id),
                "email": msg.sender.email,
            },
            "content": msg.content[:50] if msg.content else None,  # Preview (safe for file/voice)
            "created_at": msg.created_at.isoformat().replace("+00:00", "Z"),
        }

    def get_unread_count(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return 0
        return obj.messages.filter(is_deleted=False).exclude(sender=request.user).exclude(reads__user=request.user, reads__read_at__isnull=False).distinct().count()

    def get_other_member(self, obj):
        """For private chats, return the other user"""
        if obj.is_group:
            return None
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        other = obj.memberships.select_related("user").exclude(user=request.user).first()
        if not other:
            return None
        return UserSerializer(other.user, context=self.context).data


class PrivateChatSerializer(serializers.Serializer):
    other_user_id = serializers.IntegerField()