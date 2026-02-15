# app/api/auth.py - API endpoints for authentication
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse
import httpx
import secrets
import logging

from app.core.database import get_db
from app.schemas.user import UserCreate, UserLogin, UserResponse, Token
from app.schemas.oauth import OAuthUserComplete
from app.services.auth import AuthService
from app.core.security import (
    decode_access_token,
    create_access_token,
)  # Add create_access_token here
from app.core.oauth import oauth
from app.core.config import settings
from app.models.user import User, UserType

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# Temporary storage for OAuth flow (use Redis in production)
oauth_temp_store = {}


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
                User.oauth_provider == "google",
                User.oauth_provider_id == oauth_provider_id,
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
        # Store OAuth data temporarily
        temp_token = secrets.token_urlsafe(32)
        oauth_temp_store[temp_token] = {
            "email": email,
            "oauth_provider": "google",
            "oauth_provider_id": oauth_provider_id,
            "full_name": user_info.get("name"),
            "avatar_url": user_info.get("picture"),
        }

        # Redirect to frontend user type selection page
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/auth/complete-signup?temp_token={temp_token}"
        )

    except Exception as e:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error={str(e)}")


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
    """Handle LinkedIn OAuth callback"""
    logger.info("=== LinkedIn OAuth Callback Received ===")

    try:
        # Log incoming request details
        logger.info(f"Request URL: {request.url}")
        logger.info(f"Query params: {dict(request.query_params)}")

        # Get the token WITHOUT parsing ID token
        logger.info("Attempting to exchange code for access token...")
        token = await oauth.linkedin.authorize_access_token(request)
        logger.info("✓ Successfully received access token from LinkedIn")
        logger.info(f"Token keys: {list(token.keys())}")

        # Get user info from LinkedIn API manually
        logger.info("Fetching user info from LinkedIn API...")
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {token['access_token']}"}

            # LinkedIn's userinfo endpoint
            response = await client.get(
                "https://api.linkedin.com/v2/userinfo", headers=headers
            )
            logger.info(f"LinkedIn API response status: {response.status_code}")

            if response.status_code != 200:
                logger.error(f"LinkedIn API error: {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"LinkedIn API error: {response.text}",
                )

            user_info = response.json()
            logger.info("✓ Successfully received user info from LinkedIn")
            logger.info(f"User info: {user_info}")

        email = user_info.get("email")
        oauth_provider_id = user_info.get("sub")

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
        logger.info("New user detected - creating temp token for signup completion")
        temp_token = secrets.token_urlsafe(32)
        oauth_temp_store[temp_token] = {
            "email": email,
            "oauth_provider": "linkedin",
            "oauth_provider_id": oauth_provider_id,
            "full_name": user_info.get("name"),
            "avatar_url": user_info.get("picture"),
        }
        logger.info(f"Stored OAuth data with temp_token: {temp_token}")

        redirect_url = (
            f"{settings.FRONTEND_URL}/auth/complete-signup?temp_token={temp_token}"
        )
        logger.info(f"Redirecting new user to: {redirect_url}")
        return RedirectResponse(url=redirect_url)

    except HTTPException as he:
        logger.error(f"HTTPException in LinkedIn callback: {he.detail}")
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error={he.detail}")
    except Exception as e:
        logger.error(f"Unexpected error in LinkedIn callback: {str(e)}", exc_info=True)
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error={str(e)}")


@router.post("/oauth/complete-signup")
async def complete_oauth_signup(
    temp_token: str, user_type: UserType, db: Session = Depends(get_db)
):
    """Complete OAuth signup by providing user_type"""
    logger.info(f"=== Complete OAuth Signup Called ===")
    logger.info(f"Temp token: {temp_token}")
    logger.info(f"User type: {user_type}")

    # Get OAuth data from temporary store
    oauth_data = oauth_temp_store.get(temp_token)
    if not oauth_data:
        logger.error(f"Invalid or expired temp_token: {temp_token}")
        logger.info(f"Available temp tokens: {list(oauth_temp_store.keys())}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired signup token",
        )

    logger.info(f"OAuth data retrieved: {oauth_data}")

    # Create user with user_type
    logger.info("Creating user with OAuth data...")
    user, is_new = AuthService.get_or_create_oauth_user(
        db=db,
        email=oauth_data["email"],
        oauth_provider=oauth_data["oauth_provider"],
        oauth_provider_id=oauth_data["oauth_provider_id"],
        full_name=oauth_data.get("full_name"),
        avatar_url=oauth_data.get("avatar_url"),
        user_type=user_type,
    )
    logger.info(f"✓ User created/retrieved: {user.email} (is_new: {is_new})")

    # Clean up temporary data
    del oauth_temp_store[temp_token]
    logger.info("✓ Cleaned up temp token")

    # Create access token
    access_token = create_access_token(data={"sub": user.email})
    logger.info("✓ Access token created")

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "user_type": user.user_type.value,
            "avatar_url": user.avatar_url,
        },
    }
