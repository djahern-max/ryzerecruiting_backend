import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import all models so SQLAlchemy can resolve all foreign keys
from app.models.user import User
from app.models.candidate import Candidate
from app.models.employer_profile import EmployerProfile
from app.models.job_order import JobOrder
from app.models.booking import Booking
from app.models.chat_session import ChatSession
from app.models.chat_message import ChatMessage
from app.models.tenant import Tenant

from app.services.embedding_service import sync_embeddings, backfill_bookings

print("Running embedding sync...")
result = sync_embeddings()
print(
    f"  ✓ Candidates: {result['candidates']}, Employers: {result['employers']}, Job Orders: {result['job_orders']}, Errors: {result['errors']}"
)

print("Running booking backfill...")
result = backfill_bookings()
print(f"  ✓ Bookings embedded: {result['embedded']}, Errors: {result['errors']}")

print("\n✅ All embeddings complete.")
