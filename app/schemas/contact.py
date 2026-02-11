# contact.py - Schema definitions for contact management
from pydantic import BaseModel, EmailStr


class ContactCreate(BaseModel):
    name: str
    email: EmailStr
    message: str


class ContactResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    message: str

    class Config:
        orm_mode = True
