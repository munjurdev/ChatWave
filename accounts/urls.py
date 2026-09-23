from django.urls import path
from accounts.admin_ban_to_user import AdminUserBanAPIView

from .views import *

urlpatterns = [
    # (Sign-Up)
    path("sign-up", SignUpAPIView.as_view(), name="sign-up"),
    path("verify-email", VerifyEmailAPIView.as_view(), name="verify-email"),
    path("resend-verification-code", ResendVerificationCodeAPIView.as_view(), name="resend-verification-code"),
    
    # (Sign-In)
    path("sign-in", SignInAPIView.as_view(), name="sign-in"),


    # (Forgot Password)
    path('forgot-password', RequestForgotPasswordView.as_view(), name='forgot-password'),
    path('verify-reset-code', VerifyResetCodeView.as_view(), name='verify-reset-code'),
    path('reset-password', ResetPasswordView.as_view(), name='reset-password'),

    # (Change Password)
    path('change-password', ChangePasswordView.as_view(), name='change-password'),

    # (Refresh to Access Token)
    path('refresh', RefreshAccessTokenView.as_view(), name='refresh'),

    # Blook, Unblock & Report User
    path("block-user-list", BlockUserListAPIView.as_view(), name="block-user-list"),
    path("block-user", BlockUserAPIView.as_view(), name="block-user"),
    path("unblock-user", UnblockUserAPIView.as_view(), name="unblock-user"),
    path("report-user", ReportUserAPIView.as_view(), name="report-user"),

]