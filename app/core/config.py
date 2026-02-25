# app/core/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # App
    SECRET_KEY: str
    APP_NAME: str = "RYZE Recruiting API"
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

    # Email (Resend) - Phase 3
    RESEND_API_KEY: str = ""
    FROM_EMAIL: str = "noreply@ryzerecruiting.com"
    ADMIN_EMAIL: str = ""

    # Zoom
    ZOOM_MEETING_URL: str = ""

    # Google Calendar - Phase 4
    GOOGLE_CALENDAR_ID: str = "primary"
    GOOGLE_REFRESH_TOKEN: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
