import json
import urllib.request
import secrets
from typing import Optional, Tuple

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail

from .models import OTP, PasswordChangeHistory, UserAccount


def generate_numeric_otp(length: int = 6) -> str:
    """Generate a cryptographically secure numeric OTP."""
    digits = "0123456789"
    return "".join(secrets.choice(digits) for _ in range(length))


def create_otp_for_user(user: UserAccount, expiry_minutes: int = 5) -> Tuple[OTP, str]:
    """
    Invalidate previous unused OTPs and create a new hashed OTP.
    Returns (otp_instance, raw_otp_code).
    """
    # Invalidate older active OTPs
    user.otps.filter(is_used=False).update(is_used=True)

    raw_otp = generate_numeric_otp(6)
    hashed_otp = make_password(raw_otp)

    otp = OTP.objects.create(
        user=user,
        otp_hash=hashed_otp,
    )
    return otp, raw_otp


def send_otp_email(user: UserAccount, raw_otp: str) -> bool:
    """
    Send verification OTP to user's email address.
    """
    subject = "Your Aibiro Verification Code"
    message = (
        f"Hello {user.full_name or user.email},\n\n"
        f"Your verification code is: {raw_otp}\n\n"
        f"This code will expire in 5 minutes. If you did not request this, please ignore this email.\n\n"
        f"Best regards,\nThe Aibiro Team"
    )
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@aibiro.com")

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return True
    except Exception:
        # In development or if SMTP is unconfigured, return False but do not crash
        return False


def verify_otp_for_user(user: UserAccount, raw_otp: str) -> Tuple[bool, str]:
    """
    Verify the provided OTP against the latest active OTP for the user.
    Returns (is_success, error_message).
    """
    active_otp: Optional[OTP] = user.otps.filter(is_used=False).order_by("-created_at").first()

    if not active_otp:
        return False, "No active verification code found. Please request a new one."

    if active_otp.is_expired():
        active_otp.is_used = True
        active_otp.save(update_fields=["is_used"])
        return False, "Verification code has expired. Please request a new one."

    if not check_password(raw_otp, active_otp.otp_hash):
        return False, "Invalid verification code."

    # Mark OTP as used and activate/verify the user
    active_otp.is_used = True
    active_otp.save(update_fields=["is_used"])

    user.is_verified = True
    user.is_active = True
    user.save(update_fields=["is_verified", "is_active"])

    return True, ""


def get_client_ip(request) -> Optional[str]:
    """Extract client IP address from request headers."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip or None


def parse_device_info(request) -> str:
    """
    Parse a human-friendly device description matching the UI
    (e.g., 'MacBook Pro (Mac OS)', 'iPhone 13 (iOS)', 'Windows PC (Windows 11)').
    Allows explicit override via headers or body.
    """
    # 1. Check explicit header or payload
    explicit_device = (
        request.data.get("device_info")
        if hasattr(request, "data") and isinstance(request.data, dict)
        else None
    ) or request.META.get("HTTP_X_DEVICE_INFO")
    if explicit_device:
        return explicit_device

    # 2. Heuristics from User-Agent
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    ua_lower = user_agent.lower()

    if "macintosh" in ua_lower or "mac os" in ua_lower:
        return "MacBook Pro (Mac OS)"
    if "iphone" in ua_lower:
        return "iPhone (iOS)"
    if "ipad" in ua_lower:
        return "iPad (iOS)"
    if "windows" in ua_lower:
        return "Windows PC (Windows 11)"
    if "android" in ua_lower:
        return "Android Device"
    if "linux" in ua_lower:
        return "Linux PC"

    return "Web Browser"


def get_client_location(request) -> str:
    """
    Extract location matching the UI (e.g., 'Lisbon, Portugal').
    Allows explicit override via header 'X-Client-Location' or body 'location'.
    """
    explicit_location = (
        request.data.get("location")
        if hasattr(request, "data") and isinstance(request.data, dict)
        else None
    ) or request.META.get("HTTP_X_CLIENT_LOCATION")

    if explicit_location:
        return explicit_location

    ip = get_client_ip(request)
    if not ip or ip in ["127.0.0.1", "::1", "localhost"]:
        return "Localhost"

    try:
        req = urllib.request.Request(f"http://ip-api.com/json/{ip}")
        with urllib.request.urlopen(req, timeout=2) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                if data.get("status") == "success":
                    city = data.get("city", "")
                    country = data.get("country", "")
                    if city and country:
                        return f"{city}, {country}"
                    elif country:
                        return country
    except Exception:
        pass

    return "Unknown Location"


def record_password_change_event(
    request,
    user: UserAccount,
    status: str,
) -> PasswordChangeHistory:
    """Record an audit trail entry for a password change attempt."""
    device_info = parse_device_info(request)
    location = get_client_location(request)
    ip_address = get_client_ip(request)
    user_agent = request.META.get("HTTP_USER_AGENT", "")

    return PasswordChangeHistory.objects.create(
        user=user,
        status=status,
        device_info=device_info,
        location=location,
        ip_address=ip_address,
        user_agent=user_agent,
    )
