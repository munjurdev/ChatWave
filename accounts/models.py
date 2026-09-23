import random
import uuid
from datetime import timedelta

import shortuuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class SoftDeleteQuerySet(models.QuerySet):
    def delete(self):
        return super().update(is_deleted=True, deleted_at=timezone.now())
    def hard_delete(self):
        return super().delete()

class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).filter(is_deleted=False)

class SoftDeleteModel(models.Model):
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    all_objects = models.Manager()
    objects = SoftDeleteManager()

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at"])

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at"])


class UserManager(BaseUserManager.from_queryset(SoftDeleteQuerySet)):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def all_objects(self):
        return super().get_queryset()

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required.")

        if not password:
            raise ValueError("Password is required.")

        extra_fields.setdefault("role", "user")

        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_verified", True)
        extra_fields.setdefault("role", "admin")

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")

        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin, SoftDeleteModel):
    ROLE_CHOICES = (
        ("admin", "Admin"),
        ("user", "User"),
    )

    id = models.CharField(
        primary_key=True,
        max_length=22,
        default=shortuuid.uuid,
        editable=False,
    )
    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=255, blank=True)
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="user",
        db_index=True,
    )

    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False, db_index=True)

    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    # ==============================
    # BAN SYSTEM
    # ==============================
    is_banned = models.BooleanField(default=False, db_index=True)
    is_permanently_banned = models.BooleanField(default=False)
    banned_at = models.DateTimeField(null=True, blank=True)
    banned_until = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True
    )
    banned_reason = models.CharField(
        max_length=255,
        blank=True
    )
    banned_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="banned_users"
    )

    # ==============================
    reset_secret_key = models.UUIDField(
        default=uuid.uuid4,
        blank=True,
        null=True,
        db_index=True,
    )
    terms_agreed = models.BooleanField(default=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["role"]),
            models.Index(fields=["is_verified"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["is_deleted"]),
            models.Index(fields=["is_banned"]),
            models.Index(fields=["banned_until"]),
        ]
    
    def check_ban(self):
        if not self.is_banned:
            return False, None

        # permanent ban
        if self.is_permanently_banned:
            return True, "Your account has been permanently banned."

        # temporary expired → auto unban
        if self.banned_until and timezone.now() >= self.banned_until:
            self.is_banned = False
            self.banned_until = None
            self.banned_at = None
            self.banned_reason = ""
            self.save(update_fields=[
                "is_banned",
                "banned_until",
                "banned_at",
                "banned_reason"
            ])
            return False, None

        # temporary active
        until = self.banned_until.strftime("%d %b %Y, %I:%M %p")
        return True, f"Your account is temporarily banned until {until}."

    def __str__(self):
        return self.email


class EmailOTP(TimeStampedModel):
    PURPOSE_CHOICES = (
        ("signup", "Signup"),
        ("signin", "Signin"),
        ("reset_password", "Reset Password"),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="email_otps",
    )
    otp = models.CharField(max_length=6, db_index=True)
    purpose = models.CharField(
        max_length=30,
        choices=PURPOSE_CHOICES,
        default="signup",
    )
    expires_at = models.DateTimeField(db_index=True)
    is_used = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "purpose"]),
            models.Index(fields=["user", "otp"]),
            models.Index(fields=["expires_at"]),
            models.Index(fields=["is_used"]),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.purpose}"

    @staticmethod
    def generate_otp():
        return f"{random.randint(100000, 999999)}"

    @staticmethod
    def default_expiry(minutes=5):
        return timezone.now() + timedelta(minutes=minutes)

    def is_expired(self):
        return timezone.now() > self.expires_at


class UserBlock(TimeStampedModel, SoftDeleteModel):
    blocked_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="blocks_initiated",
    )
    blocked_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="blocked_by_users",
    )

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("blocked_by", "blocked_user")
        indexes = [
            models.Index(fields=["blocked_by"]),
            models.Index(fields=["blocked_user"]),
            models.Index(fields=["is_deleted"]),
        ]

    def __str__(self):
        return f"{self.blocked_by.email} blocked {self.blocked_user.email}"


class UserReport(TimeStampedModel, SoftDeleteModel):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("reviewed", "Reviewed"),
        ("dismissed", "Dismissed"),
    )

    reporter = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="reports_made",
    )
    reported_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="reports_received",
    )
    reason = models.CharField(max_length=255)
    details = models.TextField(blank=True)
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["reporter"]),
            models.Index(fields=["reported_user"]),
            models.Index(fields=["status"]),
            models.Index(fields=["is_deleted"]),
        ]

    def __str__(self):
        return f"Report by {self.reporter.email} against {self.reported_user.email}: {self.reason}"