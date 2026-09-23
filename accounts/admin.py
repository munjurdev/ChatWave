from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, EmailOTP, UserBlock, UserReport


# =========================
# USER ADMIN
# =========================
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User

    list_display = (
        "id",
        "email",
        "role",
        "is_verified",
        "is_active",
        "is_banned",
        "is_permanently_banned",
        "banned_until",
        "is_staff",
        "is_superuser",
    )

    list_filter = (
        "role",
        "is_verified",
        "is_active",
        "is_banned",
        "is_permanently_banned",
        "is_staff",
        "is_superuser",
        "is_deleted",
    )

    search_fields = ("id", "email")
    ordering = ("-id",)

    readonly_fields = (
        "id",
        "reset_secret_key",
        "last_login",
        "banned_at",
    )

    fieldsets = (
        ("Basic Info", {
            "fields": (
                "id",
                "email",
                "password",
                "role",
            )
        }),

        ("Permissions", {
            "fields": (
                "is_active",
                "is_verified",
                "is_staff",
                "is_superuser",
                "groups",
                "user_permissions",
            )
        }),

        ("BAN SYSTEM", {
            "fields": (
                "is_banned",
                "is_permanently_banned",
                "banned_at",
                "banned_until",
                "banned_reason",
                "banned_by",
            )
        }),

        ("Security", {
            "fields": (
                "last_login",
                "reset_secret_key",
                "terms_agreed",
            )
        }),

        ("Soft Delete", {
            "fields": (
                "is_deleted",
                "deleted_at",
            )
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("banned_by")


# =========================
# EMAIL OTP ADMIN
# =========================
@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "otp",
        "purpose",
        "is_used",
        "expires_at",
        "created_at",
    )

    list_filter = (
        "purpose",
        "is_used",
        "expires_at",
        "created_at",
    )

    search_fields = (
        "user__email",
        "otp",
    )

    autocomplete_fields = ("user",)

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
    )

    ordering = ("-created_at",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")


# =========================
# USER BLOCK ADMIN
# =========================
@admin.register(UserBlock)
class UserBlockAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "blocked_by",
        "blocked_user",
        "created_at",
        "is_deleted",
    )

    list_filter = (
        "created_at",
        "is_deleted",
    )

    search_fields = (
        "blocked_by__email",
        "blocked_user__email",
    )

    autocomplete_fields = (
        "blocked_by",
        "blocked_user",
    )

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
    )

    ordering = ("-created_at",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "blocked_by",
            "blocked_user"
        )


# =========================
# USER REPORT ADMIN
# =========================
@admin.register(UserReport)
class UserReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "reporter",
        "reported_user",
        "reason",
        "status",
        "created_at",
        "is_deleted",
    )

    list_filter = (
        "status",
        "created_at",
        "is_deleted",
    )

    search_fields = (
        "reporter__email",
        "reported_user__email",
        "reason",
        "details",
    )

    autocomplete_fields = (
        "reporter",
        "reported_user",
    )

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
    )

    ordering = ("-created_at",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "reporter",
            "reported_user"
        )