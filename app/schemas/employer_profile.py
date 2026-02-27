from typing import Optional
from pydantic import BaseModel


class UpdateRecruiterNotes(BaseModel):
    recruiter_notes: Optional[str] = None
    relationship_status: Optional[str] = None
