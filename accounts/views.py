from django.contrib.auth import authenticate
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken, TokenError, OutstandingToken, BlacklistedToken

from django.utils import timezone

from .utils import error_response, get_page_params, paginate_queryset, success_response
from .permissions import IsNotBanned

from .models import EmailOTP, User, UserBlock, UserReport
from .services import create_email_otp


# ---------------------------------------------------------
# SignUp
# ---------------------------------------------------------
class SignUpAPIView(APIView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        email = (request.data.get("email_address") or "").strip().lower()
        password = request.data.get("password") or ""
        full_name = (request.data.get("full_name") or "").strip()

        if not email:
            return Response(
                error_response("Email is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not password:
            return Response(
                error_response("Password is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        if not full_name:
            return Response(
                error_response("Full Name is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing_user = User.objects.filter(email=email).first()
        if existing_user:
            if existing_user.is_verified:
                return Response(
                    error_response("An account with this email already exists. Please sign in instead."),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            existing_user.set_password(password)
            existing_user.full_name = full_name
            existing_user.save()

            otp = create_email_otp(user=existing_user, purpose="signup")

            return Response(
                success_response(
                    "An OTP has been sent to your email. Please verify your account to continue.",
                    {
                        "user_id": existing_user.id,
                        "debug_otp": otp,  # remove in production
                    },
                ),
                status=status.HTTP_200_OK,
            )

        user = User.objects.create_user(email=email, password=password, full_name=full_name)
        otp = create_email_otp(user=user, purpose="signup")

        return Response(
            success_response(
                "An OTP has been sent to your email. Please verify your account to continue.",
                {
                    "user_id": user.id,
                    "debug_otp": otp,  # remove in production
                },
            ),
            status=status.HTTP_201_CREATED,
        )
    

# ---------------------------------------------------------
# Verify Email
# ---------------------------------------------------------
class VerifyEmailAPIView(APIView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        user_id = (request.data.get("user_id") or "").strip()
        verification_code = (request.data.get("verification_code") or "").strip()

        if not user_id:
            return Response(
                error_response("User ID is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not verification_code:
            return Response(
                error_response("Verification code is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                error_response("User not found."),
                status=status.HTTP_404_NOT_FOUND,
            )

        if user.is_verified and user.is_active:
            return Response(
                error_response("Account is already verified. Please sign in."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        otp_obj = (
            EmailOTP.objects.filter(
                user=user,
                otp=verification_code,
                is_used=False,
                purpose="signup",
            )
            .order_by("-created_at")
            .first()
        )

        if not otp_obj:
            return Response(
                error_response("Invalid verification code."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if otp_obj.is_expired():
            return Response(
                error_response("Verification code has expired. Please request a new one."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        otp_obj.is_used = True
        otp_obj.save(update_fields=["is_used", "updated_at"])

        user.is_verified = True
        user.is_active = True
        user.save(update_fields=["is_verified", "is_active"])

        refresh = RefreshToken.for_user(user)
        access_token = refresh.access_token

        expires_in = int(access_token.lifetime.total_seconds() * 1000)
        expires_at = int((timezone.now() + access_token.lifetime).timestamp() * 1000)

        onboarding_completed = True
        is_photo_uploaded = bool(user.avatar)

        return Response(
            success_response(
                "Account verified successfully.",
                {
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "role": user.role,
                        "is_verified": user.is_verified,
                        "is_active": user.is_active,
                    },
                    "tokens": {
                        "access": str(access_token),
                        "refresh": str(refresh),
                        "token_type": "Bearer",
                        "expires_in": expires_in,
                        "expires_at": expires_at,
                    },
                    "onboarding": {
                        "completed": onboarding_completed,
                        "is_photo_uploaded": is_photo_uploaded,
                    },
                },
            ),
            status=status.HTTP_200_OK,
        )

# ---------------------------------------------------------
# Resend Verification Code
# ---------------------------------------------------------
class ResendVerificationCodeAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        user_id = (request.data.get("user_id") or "").strip()

        if not user_id:
            return Response(
                error_response("User ID is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                error_response("User not found."),
                status=status.HTTP_404_NOT_FOUND,
            )

        if user.is_verified:
            return Response(
                error_response("Account is already verified. Please sign in instead."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        otp = create_email_otp(user=user, purpose="signup")

        return Response(
            success_response(
                "A one-time verification code has been sent to your email address.",
                {
                    "user_id": user.id,
                    "debug_otp": otp,  # remove in production
                },
            ),
            status=status.HTTP_200_OK,
        )
    

# ---------------------------------------------------------
# SignIn
# ---------------------------------------------------------
class SignInAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = (request.data.get("email_address") or "").strip().lower()
        password = request.data.get("password") or ""

        if not email:
            return Response(
                error_response("Email is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not password:
            return Response(
                error_response("Password is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request, email=email, password=password)

        if not user:
            return Response(
                error_response("Invalid email or password."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.is_verified:
            return Response(
                error_response("Please verify your account before signing in."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.is_active:
            return Response(
                error_response("Your account is inactive. Please contact support."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # BAN CHECK (NEW ADDITION)
        is_banned, message = user.check_ban()
        if is_banned:
            return Response(
                error_response(message),
                status=status.HTTP_403_FORBIDDEN,
            )

        # TOKEN GENERATION
        refresh = RefreshToken.for_user(user)
        access_token = refresh.access_token

        expires_in = int(access_token.lifetime.total_seconds() * 1000)
        expires_at = int((timezone.now() + access_token.lifetime).timestamp() * 1000)

        onboarding_completed = True
        is_photo_uploaded = bool(user.avatar)

        return Response(
            success_response(
                "Sign in successful.",
                {
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "role": user.role,
                        "is_verified": user.is_verified,
                        "is_active": user.is_active,
                    },
                    "tokens": {
                        "access": str(access_token),
                        "refresh": str(refresh),
                        "token_type": "Bearer",
                        "expires_in": expires_in,
                        "expires_at": expires_at,
                    },
                    "onboarding": {
                        "completed": onboarding_completed,
                        "is_photo_uploaded": is_photo_uploaded,
                    },
                },
            ),
            status=status.HTTP_200_OK,
        )
    
    
# ---------------------------------------------------------
# Forgot Password: Request Reset Code
# ---------------------------------------------------------
class RequestForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = (request.data.get("email_address") or "").strip().lower()

        if not email:
            return Response(
                error_response("Email is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.filter(email=email).first()
        if not user:
            return Response(
                error_response("User not found."),
                status=status.HTTP_404_NOT_FOUND,
            )

        # IMPORTANT CHECK
        if not user.is_verified:
            return Response(
                error_response(
                    "Your account is not verified. Please verify your email first."
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.is_active:
            return Response(
                error_response(
                    "Your account is inactive. Please contact support."
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ---------------- CREATE OTP ----------------
        otp = create_email_otp(user=user, purpose="reset_password")

        return Response(
            success_response(
                "A password reset code has been sent to your email address.",
                {
                    "user_id": user.id,
                    "debug_otp": otp,  # remove in production
                },
            ),
            status=status.HTTP_200_OK,
        )
    

# ---------------------------------------------------------
# Forgot Password: Verify Reset Code
# ---------------------------------------------------------
class VerifyResetCodeView(APIView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        user_id = (request.data.get("user_id") or "").strip()
        verification_code = (request.data.get("verification_code") or "").strip()

        if not user_id:
            return Response(
                error_response("User ID is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not verification_code:
            return Response(
                error_response("Verification code is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                error_response("User not found."),
                status=status.HTTP_404_NOT_FOUND,
            )

        otp_obj = (
            EmailOTP.objects.filter(
                user=user,
                otp=verification_code,
                is_used=False,
                purpose="reset_password",
            )
            .order_by("-created_at")
            .first()
        )

        if not otp_obj:
            return Response(
                error_response("Invalid reset code."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if otp_obj.is_expired():
            return Response(
                error_response("Reset code has expired. Please request a new one."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        otp_obj.is_used = True
        otp_obj.save(update_fields=["is_used", "updated_at"])

        # generate new reset secret key every successful verification
        import uuid
        user.reset_secret_key = uuid.uuid4()
        user.save(update_fields=["reset_secret_key"])

        return Response(
            success_response(
                "Reset code verified successfully.",
                {
                    "user_id": user.id,
                    "secret_key": str(user.reset_secret_key),
                },
            ),
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------
# Forgot Password: Reset Password
# ---------------------------------------------------------
class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        user_id = (request.data.get("user_id") or "").strip()
        secret_key = (request.data.get("secret_key") or "").strip()
        new_password = request.data.get("new_password") or ""
        confirm_password = request.data.get("confirm_password") or ""

        if not user_id:
            return Response(
                error_response("User ID is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not secret_key:
            return Response(
                error_response("Reset token is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not new_password:
            return Response(
                error_response("New password is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not confirm_password:
            return Response(
                error_response("Confirm password is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if new_password != confirm_password:
            return Response(
                error_response("New password and confirm password do not match."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                error_response("User not found."),
                status=status.HTTP_404_NOT_FOUND,
            )

        if str(user.reset_secret_key) != secret_key:
            return Response(
                error_response("Invalid reset token."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(new_password)

        import uuid
        user.reset_secret_key = uuid.uuid4()
        user.save(update_fields=["password", "reset_secret_key"])

        return Response(
            success_response(
                "Password has been reset successfully.",
                {
                    "user_id": user.id,
                },
            ),
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------
# Change Password
# ---------------------------------------------------------
class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated, IsNotBanned]

    @transaction.atomic
    def post(self, request):
        user = request.user
        current_password = request.data.get("current_password") or ""
        new_password = request.data.get("new_password") or ""
        confirm_password = request.data.get("confirm_password") or ""

        if not current_password:
            return Response(
                error_response("Current password is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not new_password:
            return Response(
                error_response("New password is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not confirm_password:
            return Response(
                error_response("Confirm password is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.check_password(current_password):
            return Response(
                error_response("Current password is incorrect."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if new_password != confirm_password:
            return Response(
                error_response("New password and confirm password do not match."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if current_password == new_password:
            return Response(
                error_response("New password must be different from the current password."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(new_password)

        import uuid
        user.reset_secret_key = uuid.uuid4()
        user.save(update_fields=["password", "reset_secret_key"])

        return Response(
            success_response(
                "Password changed successfully.",
                {
                    "user_id": user.id,
                },
            ),
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------
# Refresh to Access Token
# ---------------------------------------------------------
class RefreshAccessTokenView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = (request.data.get("refresh_token") or "").strip()

        if not refresh_token:
            return Response(
                error_response("Refresh token is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            refresh = RefreshToken(refresh_token)
            access_token = refresh.access_token

            expires_in = int(access_token.lifetime.total_seconds() * 1000)
            expires_at = int((timezone.now() + access_token.lifetime).timestamp() * 1000)

            return Response(
                success_response(
                    "Access token refreshed successfully.",
                    {
                        "tokens": {
                            "access": str(access_token),
                            "refresh": str(refresh),
                            "token_type": "Bearer",
                            "expires_in": expires_in,
                            "expires_at": expires_at,
                        }
                    },
                ),
                status=status.HTTP_200_OK,
            )

        except TokenError:
            return Response(
                error_response("Invalid or expired refresh token."),
                status=status.HTTP_400_BAD_REQUEST,
            )
        

# ---------------------------------------------------------
# My Account
# ---------------------------------------------------------
class MyAccountAPIView(APIView):
    permission_classes = [IsAuthenticated, IsNotBanned]

    def get(self, request):
        user = request.user
        is_photo_uploaded = bool(user.avatar)

        return Response(
            success_response(
                "Account retrieved successfully.",
                {
                    "id": user.id,
                    "email": user.email,
                    "role": user.role,
                    "is_verified": user.is_verified,
                    "full_name": user.full_name,
                    "avatar": request.build_absolute_uri(user.avatar.url) if user.avatar else None,
                },
            )
        )
    

# ---------------------------------------------------------
# Block User List
# ---------------------------------------------------------
class BlockUserListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        queryset = (
            UserBlock.all_objects
            .select_related("blocked_user")
            .filter(blocked_by=user, is_deleted=False)
            .order_by("-created_at")
        )

        page, page_size = get_page_params(request)
        paginated = paginate_queryset(queryset, page, page_size)

        from chat.serializers import UserSerializer
        results = [
            {
                "id": block.id,
                "blocked_user": UserSerializer(block.blocked_user, context={"request": request}).data,
                "created_at": block.created_at,
            }
            for block in paginated["items"]
        ]

        return Response(
            success_response(
                "Blocked users retrieved successfully.",
                {
                    "total": paginated["total"],
                    "page": paginated["page"],
                    "page_size": paginated["page_size"],
                    "total_pages": paginated["total_pages"],
                    "results": results,
                },
            ),
            status=status.HTTP_200_OK,
        )
    


# ---------------------------------------------------------
# Block User
# ---------------------------------------------------------
class BlockUserAPIView(APIView):
    permission_classes = [IsAuthenticated, IsNotBanned]

    def post(self, request):
        target_user_id = (request.data.get("target_user_id") or "").strip()

        if not target_user_id:
            return Response(
                error_response("Target user ID is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if target_user_id == request.user.id:
            return Response(
                error_response("You cannot block yourself."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        target_user = User.objects.filter(id=target_user_id).first()
        if not target_user:
            return Response(
                error_response("Target user not found."),
                status=status.HTTP_404_NOT_FOUND,
            )

        if target_user.role == "admin" or target_user.is_superuser:
            return Response(
                error_response("You cannot block an admin account."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        block = UserBlock.all_objects.filter(
            blocked_by=request.user,
            blocked_user=target_user,
        ).first()

        if block and not block.is_deleted:
            return Response(
                error_response("User is already blocked."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if block and block.is_deleted:
            block.restore()
        else:
            UserBlock.objects.create(
                blocked_by=request.user,
                blocked_user=target_user,
            )

        return Response(
            success_response(
                "User blocked successfully.",
                {
                    "blocked_user": {
                        "id": target_user.id,
                        "email": target_user.email,
                    }
                },
            ),
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------
# Unblock User
# ---------------------------------------------------------
class UnblockUserAPIView(APIView):
    permission_classes = [IsAuthenticated, IsNotBanned]

    def post(self, request):
        target_user_id = (
            request.data.get("target_user_id")
            or request.data.get("user_id")
            or ""
        ).strip()

        if not target_user_id:
            return Response(
                error_response("Target user ID is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if target_user_id == request.user.id:
            return Response(
                error_response("You cannot unblock yourself."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        target_user = User.objects.filter(id=target_user_id).first()
        if not target_user:
            return Response(
                error_response("Target user not found."),
                status=status.HTTP_404_NOT_FOUND,
            )

        block = UserBlock.all_objects.filter(
            blocked_by=request.user,
            blocked_user=target_user,
            is_deleted=False,
        ).first()

        if not block:
            return Response(
                error_response("No active block found for this user."),
                status=status.HTTP_404_NOT_FOUND,
            )

        block.delete()

        return Response(
            success_response(
                "User unblocked successfully.",
                {
                    "unblocked_user": {
                        "id": target_user.id,
                        "email": target_user.email,
                    }
                },
            ),
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------
# Report User
# ---------------------------------------------------------
class ReportUserAPIView(APIView):
    permission_classes = [IsAuthenticated, IsNotBanned]

    def post(self, request):
        reported_user_id = (
            request.data.get("reported_user_id")
            or request.data.get("user_id")
            or ""
        ).strip()
        reason = (request.data.get("reason") or "").strip()
        details = (request.data.get("details") or "").strip()

        if not reported_user_id:
            return Response(
                error_response("Reported user ID is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not reason:
            return Response(
                error_response("Reason is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if reported_user_id == request.user.id:
            return Response(
                error_response("You cannot report yourself."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        reported_user = User.objects.filter(id=reported_user_id).first()
        if not reported_user:
            return Response(
                error_response("Reported user not found."),
                status=status.HTTP_404_NOT_FOUND,
            )

        if reported_user.role == "admin" or reported_user.is_superuser:
            return Response(
                error_response("You cannot report an admin account."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        report = UserReport.objects.create(
            reporter=request.user,
            reported_user=reported_user,
            reason=reason,
            details=details,
        )

        return Response(
            success_response(
                "Report submitted successfully.",
                {
                    "report_id": report.id,
                    "reported_user": {
                        "id": reported_user.id,
                        "email": reported_user.email,
                    },
                    "reason": report.reason,
                    "details": report.details,
                    "status": report.status,
                },
            ),
            status=status.HTTP_201_CREATED,
        )
    
