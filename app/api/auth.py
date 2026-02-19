# app/api/auth.py - Updated to use Redis for OAuth temp storage
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse
import httpx
import secrets
import logging
import redis
import json

from app.core.database import get_db
from app.schemas.user import UserCreate, UserLogin, UserResponse, Token
from app.schemas.oauth import OAuthUserComplete
from app.services.auth import AuthService
from app.core.security import (
    decode_access_token,
    create_access_token,
)
from app.core.oauth import oauth
from app.core.config import settings
from app.models.user import User, UserType

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# ✅ NEW: Redis client for OAuth temp storage
redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)


# Helper functions for Redis OAuth storage
def store_oauth_temp_data(temp_token: str, data: dict, expiration_seconds: int = 300):
    """Store OAuth temp data in Redis with expiration (default 5 minutes)"""
    redis_client.setex(f"oauth_temp:{temp_token}", expiration_seconds, json.dumps(data))


def get_oauth_temp_data(temp_token: str) -> dict:
    """Retrieve OAuth temp data from Redis"""
    data = redis_client.get(f"oauth_temp:{temp_token}")
    if data:
        return json.loads(data)
    return None


def delete_oauth_temp_data(temp_token: str):
    """Delete OAuth temp data from Redis"""
    redis_client.delete(f"oauth_temp:{temp_token}")


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
def register(user: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user.
    """
    try:
        return AuthService.create_user(db, user)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during registration: {str(e)}",
        )


@router.post("/login", response_model=Token)
def login(user: UserLogin, db: Session = Depends(get_db)):
    """
    Login and get access token.
    """
    return AuthService.authenticate_user(db, user)


@router.post("/login/form", response_model=Token)
def login_form(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    """
    Login using OAuth2 password flow (for interactive API docs).
    """
    user_login = UserLogin(email=form_data.username, password=form_data.password)
    return AuthService.authenticate_user(db, user_login)


@router.get("/me", response_model=UserResponse)
def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    """
    Get current authenticated user.
    """
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email = payload.get("sub")
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = AuthService.get_user_by_email(db, email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


# Google OAuth Routes
@router.get("/oauth/google")
async def google_login(request: Request):
    """Initiate Google OAuth flow"""
    redirect_uri = f"{settings.BACKEND_URL}/api/auth/oauth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/oauth/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    """Handle Google OAuth callback"""
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get("userinfo")

        if not user_info:
            raise HTTPException(status_code=400, detail="Failed to get user info")

        email = user_info["email"]
        oauth_provider_id = user_info["sub"]

        # Check if user already exists
        existing_user = (
            db.query(User)
            .filter(
                (User.oauth_provider_id == oauth_provider_id)
                | (User.email == email)  # ✅ fallback: same email, different provider
            )
            .first()
        )

        if existing_user:
            # User exists - log them in
            access_token = create_access_token(data={"sub": existing_user.email})
            return RedirectResponse(
                url=f"{settings.FRONTEND_URL}/auth/callback?token={access_token}"
            )

        # New user - need to collect user_type
        # Store OAuth data temporarily in Redis (expires in 5 minutes)
        temp_token = secrets.token_urlsafe(32)
        store_oauth_temp_data(
            temp_token,
            {
                "email": email,
                "oauth_provider": "google",
                "oauth_provider_id": oauth_provider_id,
                "full_name": user_info.get("name"),
                "avatar_url": user_info.get("picture"),
            },
        )

        # Redirect to frontend user type selection page
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/auth/complete-signup?temp_token={temp_token}"
        )

    except Exception as e:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/auth?error={str(e)}")


# LinkedIn OAuth Routes
@router.get("/oauth/linkedin")
async def linkedin_login(request: Request):
    """Initiate LinkedIn OAuth flow"""
    logger.info("=== LinkedIn OAuth Login Initiated ===")
    redirect_uri = f"{settings.BACKEND_URL}/api/auth/oauth/linkedin/callback"
    logger.info(f"Redirect URI: {redirect_uri}")
    return await oauth.linkedin.authorize_redirect(request, redirect_uri)


@router.get("/oauth/linkedin/callback")
async def linkedin_callback(request: Request, db: Session = Depends(get_db)):
    """Handle LinkedIn OAuth callback - Manual token exchange"""
    logger.info("=== LinkedIn OAuth Callback Received ===")

    try:
        # Get the authorization code from query params
        code = request.query_params.get("code")
        error = request.query_params.get("error")

        if error:
            logger.error(f"OAuth error from LinkedIn: {error}")
            raise HTTPException(
                status_code=400, detail=f"LinkedIn OAuth error: {error}"
            )

        if not code:
            logger.error("No authorization code received")
            raise HTTPException(
                status_code=400, detail="No authorization code received"
            )

        logger.info(f"Authorization code received: {code[:20]}...")

        # Manually exchange code for token
        async with httpx.AsyncClient() as client:
            logger.info("Exchanging authorization code for access token...")
            token_response = await client.post(
                "https://www.linkedin.com/oauth/v2/accessToken",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": f"{settings.BACKEND_URL}/api/auth/oauth/linkedin/callback",
                    "client_id": settings.LINKEDIN_CLIENT_ID,
                    "client_secret": settings.LINKEDIN_CLIENT_SECRET,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if token_response.status_code != 200:
                logger.error(f"Token exchange failed: {token_response.text}")
                raise HTTPException(
                    status_code=token_response.status_code,
                    detail=f"Failed to exchange code for token: {token_response.text}",
                )

            token_data = token_response.json()
            access_token = token_data.get("access_token")
            logger.info("✓ Successfully exchanged code for access token")

            # Get user info from LinkedIn's userinfo endpoint
            logger.info("Fetching user info from LinkedIn...")
            user_response = await client.get(
                "https://api.linkedin.com/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if user_response.status_code != 200:
                logger.error(f"Failed to get user info: {user_response.text}")
                raise HTTPException(
                    status_code=user_response.status_code,
                    detail=f"Failed to get user info: {user_response.text}",
                )

            user_info = user_response.json()
            logger.info("✓ Successfully received user info")
            logger.info(f"User info: {user_info}")

        # Extract user data
        email = user_info.get("email")
        oauth_provider_id = user_info.get("sub")
        full_name = user_info.get("name")
        avatar_url = user_info.get("picture")

        if not email:
            logger.error("No email in user_info!")
            raise HTTPException(
                status_code=400, detail="No email received from LinkedIn"
            )

        if not oauth_provider_id:
            logger.error("No sub (provider ID) in user_info!")
            raise HTTPException(
                status_code=400, detail="No user ID received from LinkedIn"
            )

        logger.info(f"Email: {email}")
        logger.info(f"Full name: {full_name}")
        logger.info(f"OAuth Provider ID: {oauth_provider_id}")

        # Check if user already exists
        logger.info("Checking if user already exists...")
        existing_user = (
            db.query(User)
            .filter(
                User.oauth_provider == "linkedin",
                User.oauth_provider_id == oauth_provider_id,
            )
            .first()
        )

        if existing_user:
            logger.info(f"✓ Existing user found: {existing_user.email}")
            access_token = create_access_token(data={"sub": existing_user.email})
            redirect_url = f"{settings.FRONTEND_URL}/auth/callback?token={access_token}"
            logger.info(f"Redirecting existing user to: {redirect_url}")
            return RedirectResponse(url=redirect_url)

        # New user - need to collect user_type
        # Store OAuth data temporarily in Redis (expires in 5 minutes)
        logger.info("New user detected - creating temp token for signup completion")
        temp_token = secrets.token_urlsafe(32)
        store_oauth_temp_data(
            temp_token,
            {
                "email": email,
                "oauth_provider": "linkedin",
                "oauth_provider_id": oauth_provider_id,
                "full_name": full_name,
                "avatar_url": avatar_url,
            },
        )
        logger.info(f"Stored OAuth data with temp_token: {temp_token}")

        redirect_url = (
            f"{settings.FRONTEND_URL}/auth/complete-signup?temp_token={temp_token}"
        )
        logger.info(f"Redirecting new user to: {redirect_url}")
        return RedirectResponse(url=redirect_url)

    except HTTPException as he:
        logger.error(f"HTTPException in LinkedIn callback: {he.detail}")
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/auth?error={he.detail}")
    except Exception as e:
        logger.error(f"Unexpected error in LinkedIn callback: {str(e)}", exc_info=True)
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/auth?error={str(e)}")


@router.post("/oauth/complete-signup")
async def complete_oauth_signup(
    temp_token: str, user_type: UserType, db: Session = Depends(get_db)
):
    oauth_data = get_oauth_temp_data(temp_token)
    if not oauth_data:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired signup token. Please try signing in again.",
        )

    try:
        # ✅ Check by email first before inserting
        existing_user = db.query(User).filter(User.email == oauth_data["email"]).first()

        if existing_user:
            # Email exists — update their OAuth info and log them in
            logger.info(
                f"Email already exists, linking OAuth to existing user: {existing_user.email}"
            )
            existing_user.oauth_provider = oauth_data["oauth_provider"]
            existing_user.oauth_provider_id = oauth_data["oauth_provider_id"]
            existing_user.avatar_url = oauth_data.get("avatar_url")
            db.commit()
            db.refresh(existing_user)
            user = existing_user
        else:
            # Truly new user — create them
            user = User(
                email=oauth_data["email"],
                full_name=oauth_data.get("full_name"),
                oauth_provider=oauth_data["oauth_provider"],
                oauth_provider_id=oauth_data["oauth_provider_id"],
                avatar_url=oauth_data.get("avatar_url"),
                user_type=user_type,
                hashed_password=None,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info(f"✓ Created new OAuth user: {user.email}")

        delete_oauth_temp_data(temp_token)
        access_token = create_access_token(data={"sub": user.email})

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "user_type": user.user_type.value,
                "oauth_provider": user.oauth_provider,
            },
        }

    except Exception as e:
        logger.error(f"Error in OAuth signup: {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create user: {str(e)}")
