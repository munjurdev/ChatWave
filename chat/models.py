import uuid
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


# ================= CHAT =================
class Chat(models.Model):
    id = models.CharField(primary_key=True, max_length=30, editable=False)
    is_group = models.BooleanField(default=False)
    name = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def save(self, *args, **kwargs):
        if not self.id:
            self.id = f"CHAT-{uuid.uuid4().hex[:12].upper()}"
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["is_group"]),
        ]


# ================= MEMBERS =================
class ChatMembership(models.Model):
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_memberships")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("chat", "user")
        indexes = [
            models.Index(fields=["chat", "user"]),
            models.Index(fields=["user"]),
        ]


# ================= MESSAGE MEDIA PATH =================
def chat_file(instance, filename):
    return f"chat/{instance.chat_id}/file/{filename}"


def chat_voice(instance, filename):
    return f"chat/{instance.chat_id}/voice/{filename}"


# ================= MESSAGE =================
class Message(models.Model):
    TYPE_CHOICES = [
        ("text", "Text"),
        ("file", "File"),
        ("voice", "Voice"),
        ("mixed", "Mixed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(User, on_delete=models.CASCADE)

    content = models.TextField(null=True, blank=True)
    file = models.FileField(upload_to=chat_file, null=True, blank=True)
    voice = models.FileField(upload_to=chat_voice, null=True, blank=True)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default="text")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    is_edited = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.voice:
            self.type = "voice"
        elif self.file and self.content:
            self.type = "mixed"
        elif self.file:
            self.type = "file"
        else:
            self.type = "text"

        super().save(*args, **kwargs)


    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["chat", "-created_at"]),
            models.Index(fields=["chat", "is_deleted"]),
            models.Index(fields=["sender"]),
        ]


# ================= READ RECEIPTS (✓✓) =================
class MessageRead(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="reads")
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    # ✅ IMPORTANT: Track both delivery and read status
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("message", "user")
        indexes = [
            models.Index(fields=["message", "user"]),
            models.Index(fields=["user"]),
        ]


# ================= REACTIONS =================
class MessageReaction(models.Model):
    REACTIONS = (
        ("heart", "❤️"),
        ("laugh", "😂"),
        ("wow", "😮"),
        ("sad", "😢"),
        ("angry", "😡"),
        ("like", "👍"),
    )

    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="reactions")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    reaction = models.CharField(max_length=10, choices=REACTIONS)

    class Meta:
        unique_together = ("message", "user")
        indexes = [
            models.Index(fields=["message", "user"]),
        ]


# ================= ONLINE STATUS =================
class UserStatus(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="status")

    is_online = models.BooleanField(default=False, db_index=True)
    last_seen = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_online"]),
            models.Index(fields=["user"]),
        ]