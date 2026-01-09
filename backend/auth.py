"""
Authentication utilities for faculty login system.
Provides password hashing, session management, and authentication dependencies.

NOTE: Uses bcrypt directly instead of passlib due to version compatibility issues.
"""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session
from .models import Faculty, get_db
from .config import settings
import logging
import secrets
import bcrypt

logger = logging.getLogger(__name__)

# HTTP Basic Auth (for initial testing, we'll use sessions in production)
security = HTTPBasic()

# Session storage (in-memory for now, move to Redis for production)
active_sessions = {}


# ==========================================
# PASSWORD UTILITIES
# ==========================================

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False


# ==========================================
# SESSION MANAGEMENT
# ==========================================

def create_session_token() -> str:
    """Generate a secure random session token."""
    return secrets.token_urlsafe(32)


def create_session(faculty_id: str, faculty_name: str, is_admin: bool, impersonated_by: Optional[str] = None) -> str:
    """Create a new session and return the session token.
    
    Args:
        faculty_id: ID of the faculty member
        faculty_name: Name of the faculty member
        is_admin: Whether the faculty member is an admin
        impersonated_by: Optional faculty ID of the admin who is impersonating this user
    """
    token = create_session_token()
    active_sessions[token] = {
        "faculty_id": faculty_id,
        "faculty_name": faculty_name,
        "is_admin": is_admin,
        "created_at": datetime.utcnow(),
        "last_activity": datetime.utcnow(),
        "impersonated_by": impersonated_by
    }
    return token


def get_session(token: str) -> Optional[dict]:
    """Get session data from token."""
    session = active_sessions.get(token)
    if session:
        # Update last activity
        session["last_activity"] = datetime.utcnow()
        
        # Check if session is expired (24 hours)
        if datetime.utcnow() - session["created_at"] > timedelta(hours=24):
            delete_session(token)
            return None
    
    return session


def delete_session(token: str):
    """Delete a session."""
    if token in active_sessions:
        del active_sessions[token]


def authenticate_faculty(faculty_id: str, password: str, db: Session) -> Optional[Faculty]:
    """Authenticate a faculty member by ID and password."""
    faculty = db.query(Faculty).filter_by(id=faculty_id.upper()).first()
    if not faculty:
        return None
    
    if not verify_password(password, faculty.password_hash):
        return None
    
    if not faculty.active:
        return None
    
    return faculty


# ==========================================
# FASTAPI DEPENDENCIES (CORE)
# ==========================================

async def get_current_user(request: Request, db: Session = Depends(get_db)) -> Faculty:
    """Get the currently authenticated user from session cookie."""
    # Check for session token in cookies
    session_token = request.cookies.get("session_token")
    
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get session data
    session = get_session(session_token)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get faculty from database
    faculty = db.query(Faculty).filter_by(id=session["faculty_id"]).first()
    if not faculty or not faculty.active:
        delete_session(session_token)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or inactive"
        )
    
    return faculty


async def get_optional_user(request: Request, db: Session = Depends(get_db)) -> Optional[Faculty]:
    """Get the current user if authenticated, None otherwise (no exception)."""
    session_token = request.cookies.get("session_token")
    
    if not session_token:
        return None
    
    session = get_session(session_token)
    if not session:
        return None
    
    faculty = db.query(Faculty).filter_by(id=session["faculty_id"]).first()
    if not faculty or not faculty.active:
        return None
    
    return faculty


# ==========================================
# FASTAPI DEPENDENCIES (SECURITY ENHANCED)
# ==========================================

def optional_get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[Faculty]:
    """
    Get current user if authenticated, None otherwise.
    For backward compatibility during migration.
    """
    try:
        # Call the async version synchronously (FastAPI handles this)
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're already in async context, just await
            return None  # Fallback for now
        return loop.run_until_complete(get_current_user(request, db))
    except HTTPException:
        return None
    except:
        return None


def require_admin(current_user: Faculty = Depends(get_current_user)) -> Faculty:
    """
    Dependency that requires admin privileges.
    Raises 403 if user is not admin.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user


def optional_require_admin(
    current_user: Optional[Faculty] = Depends(get_optional_user)
) -> Optional[Faculty]:
    """
    Optionally require admin - for transitional period.
    Returns None if no auth, raises 403 if auth but not admin.
    """
    if settings.SECURITY_MODE == "strict":
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        if not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Admin privileges required")
        return current_user
    
    if settings.SECURITY_MODE == "transitional":
        # Warn but allow access
        if not current_user:
            logger.warning("Unauthenticated admin access in transitional mode")
            return None
        if not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Admin privileges required")
        return current_user
    
    # Permissive mode - allow everything
    return current_user


# ==========================================
# SECURITY ENHANCED FUNCTIONS
# ==========================================

def check_account_locked(faculty: Faculty) -> None:
    """Check if account is locked due to failed login attempts"""
    if faculty.account_locked_until:
        if datetime.utcnow() < faculty.account_locked_until:
            remaining = (faculty.account_locked_until - datetime.utcnow()).seconds // 60
            raise HTTPException(
                status_code=403,
                detail=f"Account locked. Try again in {remaining} minutes."
            )
        else:
            # Unlock account
            faculty.account_locked_until = None
            faculty.failed_login_attempts = 0


def handle_failed_login(db: Session, faculty: Faculty) -> None:
    """Handle failed login attempt"""
    faculty.failed_login_attempts += 1
    
    # Lock account after 5 failed attempts
    if faculty.failed_login_attempts >= 5:
        faculty.account_locked_until = datetime.utcnow() + timedelta(minutes=30)
        logger.warning(f"Account locked for {faculty.id} after {faculty.failed_login_attempts} failed attempts")
    
    db.commit()


def handle_successful_login(db: Session, faculty: Faculty, request: Request) -> None:
    """Handle successful login"""
    faculty.failed_login_attempts = 0
    faculty.account_locked_until = None
    faculty.last_login_at = datetime.utcnow()
    faculty.last_login_ip = request.client.host if request.client else None
    db.commit()
