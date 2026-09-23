"""
Context processor exposing site-wide metadata (branding + absolute URLs)
used by the Open Graph / Twitter Card meta tags in templates.
"""
from django.conf import settings


def site_meta(request):
    """Expose SITE_NAME and SITE_URL (absolute base URL) to all templates."""
    # Prefer a explicitly configured public URL, fall back to the request host.
    site_url = getattr(settings, "SITE_URL", "") or request.build_absolute_uri("/").rstrip("/")
    return {
        "SITE_NAME": "ChatWave",
        "SITE_URL": site_url,
    }
