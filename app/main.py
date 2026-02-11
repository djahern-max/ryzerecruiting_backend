# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import contact, blog
from app.core.database import engine, Base

app = FastAPI(title="RYZE Recruiting API")

# Create database tables on startup
Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change to your domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(contact.router, prefix="/contact", tags=["contact"])
app.include_router(blog.router, prefix="/blog", tags=["blog"])


@app.get("/")
async def read_root():
    return {"message": "It Works!"}
