from django.utils import timezone
from datetime import timedelta

from rest_framework.views import APIView
from rest_framework import status
from rest_framework.response import Response

from .utils import error_response, success_response
from accounts.models import User


class AdminUserBanAPIView(APIView):

    def post(self, request, user_id):
        # ROLE CHECK
        if not request.user.is_authenticated or request.user.role != "admin":
            return Response(
                error_response("Permission denied."),
                status=status.HTTP_403_FORBIDDEN,
            )

        action = request.data.get("action")
        reason = request.data.get("reason", "")
        days = request.data.get("days")

        user = User.objects.filter(id=user_id, is_deleted=False).first()

        if not user:
            return Response(
                error_response("User not found."),
                status=status.HTTP_404_NOT_FOUND,
            )

        # TEMPORARY BAN
        if action == "temporary":
            if not days:
                return Response(
                    error_response("Days are required."),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user.is_banned = True
            user.is_permanently_banned = False
            user.banned_reason = reason
            user.banned_at = timezone.now()
            user.banned_until = timezone.now() + timedelta(days=int(days))
            user.banned_by = request.user

        # PERMANENT BAN
        elif action == "permanent":
            user.is_banned = True
            user.is_permanently_banned = True
            user.banned_reason = reason
            user.banned_at = timezone.now()
            user.banned_until = None
            user.banned_by = request.user

        # UNBAN
        elif action == "unban":
            user.is_banned = False
            user.is_permanently_banned = False
            user.banned_reason = ""
            user.banned_at = None
            user.banned_until = None
            user.banned_by = None

        else:
            return Response(
                error_response("Invalid action."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.save()

        return Response(
            success_response(f"User {action} successful."),
            status=status.HTTP_200_OK,
        )