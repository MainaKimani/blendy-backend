"""
Django settings for blendy_backend project.
"""

from datetime import timedelta
import os
from pathlib import Path
from corsheaders.defaults import default_headers

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-cdtpzpu4fj_sl*551t@rj(&$p+p@o7ra9jgj2f1ekdk-hy6k(w"

PAYMENTS_MPESA_WEBHOOK_SECRET = os.getenv("PAYMENTS_MPESA_WEBHOOK_SECRET", "secret-webhook-key")

# --- M-Pesa callback authentication -----------------------------------------
# Safaricom does not sign STK callbacks, so the callback is authenticated by an
# unguessable token in the URL plus a source-IP allowlist. The token must match
# the path in MPESA_CALLBACK_URL registered with Daraja.
MPESA_WEBHOOK_TOKEN = os.getenv("MPESA_WEBHOOK_TOKEN", "")

# Verify the published Safaricom egress ranges against current Daraja docs
# before relying on this list in production.
MPESA_WEBHOOK_IP_ALLOWLIST = [
    ip.strip()
    for ip in os.getenv(
        "MPESA_WEBHOOK_IP_ALLOWLIST",
        "196.201.214.200,196.201.214.206,196.201.213.114,196.201.214.207,"
        "196.201.214.208,196.201.213.44,196.201.212.127,196.201.212.138,"
        "196.201.212.129,196.201.212.136,196.201.212.74,196.201.212.69",
    ).split(",")
    if ip.strip()
]

# Disable only for local sandbox testing through a tunnel, where the source IP
# is the tunnel's rather than Safaricom's.
MPESA_WEBHOOK_ENFORCE_IP = (
    os.getenv("MPESA_WEBHOOK_ENFORCE_IP", "true").lower() == "true"
)

# Only enable behind a proxy that overwrites X-Forwarded-For; otherwise the
# header is caller-controlled and the IP allowlist becomes meaningless.
MPESA_WEBHOOK_TRUST_FORWARDED_FOR = (
    os.getenv("MPESA_WEBHOOK_TRUST_FORWARDED_FOR", "false").lower() == "true"
)

# --- Direct (C2B) payment reconciliation ------------------------------------
# How long a sale left in AWAITING_DIRECT_PAYMENT stays eligible to be matched
# against an inbound direct payment.
MPESA_DIRECT_MATCH_WINDOW_HOURS = int(
    os.getenv("MPESA_DIRECT_MATCH_WINDOW_HOURS", "24")
)

# Permitted difference between the amount paid and the sale total. Zero means
# exact match; anything else is surfaced for manual matching instead.
MPESA_DIRECT_MATCH_TOLERANCE = os.getenv("MPESA_DIRECT_MATCH_TOLERANCE", "0.00")

# The Till/Paybill this deployment collects on. Used to attribute inbound C2B
# confirmations while organizations have no per-tenant shortcode of their own.
MPESA_SHORTCODE = os.getenv("MPESA_SHORTCODE", "")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ["*"]


# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party apps
    "rest_framework",
    "drf_yasg",  # Added for Swagger UI
    "rest_framework_simplejwt",
    "corsheaders",
    "django_extensions",
    "django_filters",
    # Local apps
    "authentication",
    "organization",
    "users",
    "authorization",
    "inventory",
    "products",
    "sales",
    "pricing",
    "payments",
]

# CORS_ALLOWED_ORIGINS = [
#     "http://localhost:4200",
# ]

CORS_ALLOW_ALL_ORIGINS = True

CORS_ALLOW_HEADERS = list(default_headers) + [
    "content-type",
    "authorization",
    "x-organization",
]

AUTH_USER_MODEL = "users.CustomUser"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_SCHEMA_CLASS": "rest_framework.schemas.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "blendy_backend.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 20,
    # Applied only to anonymous payment creation; see payments/throttles.py.
    "DEFAULT_THROTTLE_RATES": {
        "stk_push_phone": os.getenv("THROTTLE_STK_PUSH_PHONE", "5/hour"),
        "stk_push_ip": os.getenv("THROTTLE_STK_PUSH_IP", "20/hour"),
    },
}


# --- Platform access log retention -------------------------------------------
# How long a cross-tenant access record is kept. This is the answer to "who
# looked at my data?", so the default is long: a shop noticing something odd in
# last quarter's figures should still be able to ask.
PLATFORM_ACCESS_LOG_RETENTION_DAYS = int(
    os.getenv("PLATFORM_ACCESS_LOG_RETENTION_DAYS", "365")
)

# A floor beneath which `prune_access_log` refuses to run at all. Pruning is a
# privileged shell operation on an audit trail, and erasing the last few days is
# exactly what someone covering their tracks would want to do. Raising the floor
# is safe; lowering it should be a deliberate, reviewed change.
PLATFORM_ACCESS_LOG_MINIMUM_RETENTION_DAYS = int(
    os.getenv("PLATFORM_ACCESS_LOG_MINIMUM_RETENTION_DAYS", "30")
)


# The published schema, and the Swagger UI it drives. Basic auth is drf-yasg's
# default and is not what this API uses; the tenancy header is added per
# operation by the generator, since no view declares it.
SWAGGER_SETTINGS = {
    "DEFAULT_GENERATOR_CLASS": "blendy_backend.schema.BlendySchemaGenerator",
    "DEFAULT_INFO": "blendy_backend.schema.API_INFO",
    "USE_SESSION_AUTH": False,
    "SECURITY_DEFINITIONS": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": (
                'JWT access token, as returned by /api/auth/login/. '
                'Send it as: Authorization: Bearer <token>'
            ),
        },
    },
}


MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "blendy_backend.middleware.OrganizationMiddleware",
    # After OrganizationMiddleware, which resolves request.organization, and
    # recording on the way out once DRF has authenticated the caller.
    "organization.middleware.PlatformAccessLogMiddleware",
]

ROOT_URLCONF = "blendy_backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "blendy_backend.wsgi.application"


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "VERIFYING_KEY": SECRET_KEY,
    "AUDIENCE": None,
    "ISSUER": None,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "TOKEN_OBTAIN_SERIALIZER": "authentication.serializers.CustomLoginSerializer",
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "static/"

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
