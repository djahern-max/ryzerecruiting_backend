# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from app.api import contact, blog, auth
from app.core.database import engine, Base
from app.core.config import settings
from app.api.bookings import router as bookings_router

app = FastAPI(title="RYZE Recruiting API")

# Create database tables on startup
Base.metadata.create_all(bind=engine)

# Add SessionMiddleware BEFORE CORS (required for OAuth)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    max_age=3600,
)

# Updated CORS - more restrictive
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ryzerecruiting.com",
        "https://www.ryzerecruiting.com",
        "http://localhost:5173",  # Local Vite dev server
        "http://localhost:3000",  # Common React dev port
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(contact.router, prefix="/contact", tags=["contact"])
app.include_router(blog.router, prefix="/blog", tags=["blog"])
app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(bookings_router)


@app.get("/")
async def read_root():
    return {"message": "It Works!"}
