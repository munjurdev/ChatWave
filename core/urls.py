
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings
from django.http import JsonResponse, HttpResponse
import os

from chat.views import AuthView, ChatWaveView, InfoPageView, LandingPageView

# --------------------------
# URL Patterns
# --------------------------
urlpatterns = [
    # Root = marketing landing page
    path('', LandingPageView.as_view(), name='home'),

    # Chat app (shows sign-in redirect if not authenticated)
    path('app/', ChatWaveView.as_view(), name='chatwave-app'),

    # Info pages (News / Features / Careers / Help)
    path('info/<str:section>/', InfoPageView.as_view(), name='info-page'),

    # Django Admin Panel
    # Optional: Change 'admin/' to 'em-secure-admin/' in production for security
    path('admin/', admin.site.urls),

    # API Endpoints
    path("api/auth/", include("accounts.urls")),

    # Chat API
    path("api/", include("chat.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)