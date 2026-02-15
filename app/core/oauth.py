# app/core/oauth.py
from authlib.integrations.starlette_client import OAuth
from app.core.config import settings

oauth = OAuth()

# Google OAuth
oauth.register(
    name="google",
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

# LinkedIn OAuth
oauth.register(
    name="linkedin",
    client_id=settings.LINKEDIN_CLIENT_ID,
    client_secret=settings.LINKEDIN_CLIENT_SECRET,
    authorize_url="https://www.linkedin.com/oauth/v2/authorization",
    authorize_params={"scope": "openid profile email"},
    access_token_url="https://www.linkedin.com/oauth/v2/accessToken",
    access_token_params=None,
    client_kwargs={"token_endpoint_auth_method": "client_secret_post"},
)
