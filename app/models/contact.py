# contact.py - Model definition for contact management
from sqlalchemy import Column, Integer, String
from app.core.database import Base


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    message = Column(String, nullable=False)
