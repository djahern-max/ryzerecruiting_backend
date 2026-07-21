# app/core/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # App
    SECRET_KEY: str
    APP_NAME: str = "RYZE.ai API"
    DEBUG: bool = False

    # OAuth - Google
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # OAuth - LinkedIn
    LINKEDIN_CLIENT_ID: str = ""
    LINKEDIN_CLIENT_SECRET: str = ""

    # URLs
    FRONTEND_URL: str = "http://localhost:5173"
    BACKEND_URL: str = "http://localhost:8000"

    # Email (Resend)
    RESEND_API_KEY: str = ""
    FROM_EMAIL: str = "dane@ryze.ai"
    REPLY_TO_EMAIL: str = ""
    ADMIN_EMAIL: str = ""

    # Zoom
    ZOOM_ACCOUNT_ID: str = ""
    ZOOM_CLIENT_ID: str = ""
    ZOOM_CLIENT_SECRET: str = ""
    ZOOM_SECRET_TOKEN: str = ""

    # Twilio SMS
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

    # Google Calendar
    GOOGLE_CALENDAR_ID: str = "primary"
    GOOGLE_REFRESH_TOKEN: str = ""
    GOOGLE_CALENDAR_CLIENT_ID: str = ""
    GOOGLE_CALENDAR_CLIENT_SECRET: str = ""

    # AI — Anthropic
    ANTHROPIC_API_KEY: str = ""

    # AI — OpenAI (embeddings)
    OPENAI_API_KEY: str = ""

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_ID: str = ""

    # DigitalOcean Spaces
    DO_SPACES_KEY: str = ""
    DO_SPACES_SECRET: str = ""
    DO_SPACES_BUCKET: str = ""
    DO_SPACES_REGION: str = "nyc3"
    DO_SPACES_ENDPOINT: str = ""
    DO_SPACES_CDN_BASE: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
