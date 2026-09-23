from django.conf import settings
from django.core.mail import send_mail

from .models import EmailOTP


def create_email_otp(user, purpose="signup", minutes=5):
    # invalidate old OTPs
    EmailOTP.objects.filter(
        user=user,
        purpose=purpose,
        is_used=False,
    ).update(is_used=True)

    otp = EmailOTP.generate_otp()

    EmailOTP.objects.create(
        user=user,
        otp=otp,
        purpose=purpose,
        expires_at=EmailOTP.default_expiry(minutes),
    )

    # -------- EMAIL CONTENT --------
    subject_map = {
        "signup": "Vybin - Verify your account",
        "reset_password": "Vybin - Reset your password",
        "signin": "Vybin - Sign in verification code",
    }

    message_map = {
        "signup": (
            f"Welcome to Vybin!\n\n"
            f"Your verification code is: {otp}\n"
            f"This code will expire in {minutes} minutes.\n\n"
            f"If you did not request this, please ignore this email.\n\n"
            f"— Vybin Team"
        ),
        "reset_password": (
            f"Vybin Password Reset\n\n"
            f"Your password reset code is: {otp}\n"
            f"This code will expire in {minutes} minutes.\n\n"
            f"If you did not request this, please ignore this email.\n\n"
            f"— Vybin Team"
        ),
        "signin": (
            f"Vybin Sign In Verification\n\n"
            f"Your sign in code is: {otp}\n"
            f"This code will expire in {minutes} minutes.\n\n"
            f"If you did not request this, please ignore this email.\n\n"
            f"— Vybin Team"
        ),
    }

    send_mail(
        subject_map.get(purpose, "Vybin - OTP Code"),
        message_map.get(purpose, f"Your OTP is {otp}"),
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )

    return otp