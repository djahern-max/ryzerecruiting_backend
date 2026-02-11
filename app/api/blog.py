# blog.py - API endpoints for blog management
from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def read_blog_root():
    return {"message": "Blog API Root"}
