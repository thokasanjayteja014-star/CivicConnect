"""Application configuration, loaded from environment variables only.

Secrets (AUTH_SECRET, AI_PROVIDER_API_KEY, MEDIA_STORAGE_*_KEY) are never
hardcoded and never returned to the frontend.
"""
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    DATABASE_URL: str = "postgresql+psycopg://civic:civic@localhost:5432/civicconnect"
    AUTH_SECRET: str = Field(default="", description="Required. HMAC secret for JWT signing.")
    ACCESS_TOKEN_TTL_MINUTES: int = 120
    MEDIA_LINK_TTL_SECONDS: int = 300
    FRONTEND_ORIGIN: str = "http://localhost:3000"
    BACKEND_BASE_URL: str = "http://localhost:8000"
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"

    # AI integration (centralized in app/ai). Empty values => AI_NOT_CONFIGURED.
    AI_PROVIDER: str = ""
    AI_PROVIDER_API_KEY: str = ""
    AI_MODEL_NAME: str = ""
    AI_BASE_URL: str = ""  # optional override of the provider endpoint
    VISION_MODEL_NAME: str = ""
    SPEECH_MODEL_NAME: str = ""
    EMBEDDING_MODEL_NAME: str = ""
    # Optional separate speech-to-text provider (e.g. groq whisper while AI_PROVIDER=xai).
    SPEECH_PROVIDER: str = ""
    SPEECH_API_KEY: str = ""
    AI_TIMEOUT_SECONDS: float = 30.0
    AI_MAX_RETRIES: int = 2

    # Media storage. If MEDIA_STORAGE_ENDPOINT is empty, a local private
    # directory is used (development only, outside any public web root).
    MEDIA_STORAGE_ENDPOINT: str = ""
    MEDIA_STORAGE_BUCKET: str = "civicconnect-media"
    MEDIA_STORAGE_ACCESS_KEY: str = ""
    MEDIA_STORAGE_SECRET_KEY: str = ""
    MEDIA_STORAGE_REGION: str = "us-east-1"
    MEDIA_LOCAL_DIR: str = "./var/media"

    # Notifications. In-app is always on; each external channel activates when configured.
    # Email: EMAIL_PROVIDER=smtp (any SMTP server, e.g. Gmail app password) or brevo (HTTP API).
    EMAIL_PROVIDER: str = ""
    EMAIL_FROM: str = ""
    EMAIL_FROM_NAME: str = "CivicConnect"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_SSL: bool = False  # True for port 465; otherwise STARTTLS
    BREVO_API_KEY: str = ""
    # SMS: SMS_PROVIDER=twilio
    SMS_PROVIDER: str = ""
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""
    # Browser push (Web Push / VAPID). Generate with: python -m app.cli generate-vapid-keys
    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY: str = ""
    VAPID_SUBJECT: str = ""  # mailto:you@example.org
    NOTIFY_EXTERNAL_SYNC: bool = False  # send in-request instead of a background thread (tests)

    # Geocoding (address search). Default: OpenStreetMap Nominatim, free, max 1 request/second.
    GEOCODER_URL: str = "https://nominatim.openstreetmap.org"
    GEOCODER_CONTACT_EMAIL: str = ""  # sent in the User-Agent as Nominatim's usage policy asks
    GEOCODER_COUNTRY_CODES: str = "in"  # comma-separated ISO codes to bias results; empty = worldwide

    # Maps (frontend tile config is public by nature; this is informational)
    MAP_PROVIDER_CONFIGURATION: str = "osm"

    # Rate limits: "count/seconds"
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_AUTH: str = "20/60"
    RATE_LIMIT_COMPLAINT_CREATE: str = "10/60"
    RATE_LIMIT_MEDIA_UPLOAD: str = "30/60"

    # Routing
    ROUTING_MAX_LOCATION_ACCURACY_M: float = 250.0
    ROUTING_RULE_VERSION: str = "routing-v1"

    # Duplicate detection (prototype thresholds, configurable)
    DUPLICATE_RADIUS_M: float = 100.0
    DUPLICATE_TEXT_SIMILARITY: float = 0.85
    DUPLICATE_LEXICAL_SIMILARITY: float = 0.35
    DUPLICATE_WINDOW_DAYS: int = 30
    DUPLICATE_IMAGE_MAX_DISTANCE: int = 10  # max dHash Hamming distance (of 64 bits) for "similar photo"

    # Public map location approximation (decimal places kept)
    PUBLIC_LOCATION_DECIMALS: int = 3


    @field_validator("DATABASE_URL")
    @classmethod
    def _psycopg_driver(cls, v: str) -> str:
        """Accept the postgres:// / postgresql:// URLs that Supabase, Neon and Render show."""
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
