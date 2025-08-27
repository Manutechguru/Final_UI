# landing_page_app/models/__init__.py
from .clients import Client
from .jobs import Job
from .candidates import Candidate
from .candidate_status_history import CandidateJDMapping
from .log import UserLog
from .user import User, UserRole
from .managers import Manager

# Optional: group into __all__ for clean imports
__all__ = [
    "Client",
    "Job",
    "Candidate",
    "CandidateJDMapping",
    "UserLog",
    "User",
    "UserRole",
    "Manager"
]
