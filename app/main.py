# app/main.py
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from app.api import contact, blog, auth
from app.core.database import engine, Base
from app.core.config import settings
from app.api.bookings import router as bookings_router
from app.api.employer_profiles import router as employer_profiles_router
from app.api.waitlist import router as waitlist_router
from app.api.webhooks import router as webhooks_router
from app.api.job_orders import router as job_orders_router
from app.api.candidates import router as candidates_router
from app.api.search import router as search_router
from app.api.chat import router as chat_router
from app.api import chat_sessions
from app.api.db_explorer import router as db_explorer_router
from app.api.admin_invite import router as admin_invite_router
from app.api.billing import router as billing_router

app = FastAPI(title="RYZE.ai API")

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    max_age=3600,
    same_site="none",
    https_only=True,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ryze.ai",
        "https://www.ryze.ai",
        "https://api.ryze.ai",
        "https://ryzerecruiting.com",
        "https://www.ryzerecruiting.com",
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(contact.router, prefix="/contact", tags=["contact"])
app.include_router(blog.router, prefix="/blog", tags=["blog"])
app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(bookings_router)
app.include_router(employer_profiles_router)
app.include_router(waitlist_router)
app.include_router(webhooks_router)
app.include_router(job_orders_router)
app.include_router(candidates_router)
app.include_router(search_router)
app.include_router(chat_router)
app.include_router(chat_sessions.router)
app.include_router(db_explorer_router)
app.include_router(admin_invite_router)
app.include_router(billing_router)


@app.get("/")
async def read_root():
    return {"message": "It Works!"}
