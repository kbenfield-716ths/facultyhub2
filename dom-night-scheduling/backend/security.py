# backend/security.py
from fastapi import Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
import secrets
import logging
from collections import defaultdict
import time

from .models import SessionLocal, Faculty, AuditLog, SessionToken
from .config import settings

logger = logging.getLogger(__name__)

# Rate limiting storage (in-memory, use Redis in production)
rate_limit_storage = defaultdict(list)

class RateLimiter:
    """Simple in-memory rate limiter"""
    
    def __init__(self, calls: int = 60, period: int = 60):
        self.calls = calls
        self.period = period
    
    async def __call__(self, request: Request):
        if not settings.RATE_LIMIT_ENABLED:
            return
        
        # Get client identifier (IP or session)
        client_id = request.client.host if request.client else "unknown"
        
        now = time.time()
        # Clean old entries
        rate_limit_storage[client_id] = [
            timestamp for timestamp in rate_limit_storage[client_id]
            if now - timestamp < self.period
        ]
        
        # Check limit
        if len(rate_limit_storage[client_id]) >= self.calls:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again later."
            )
        
        # Add current request
        rate_limit_storage[client_id].append(now)


# Rate limiter instances
standard_limiter = RateLimiter(calls=settings.RATE_LIMIT_PER_MINUTE, period=60)
strict_limiter = RateLimiter(calls=10, period=60)  # For sensitive operations


def log_audit(
    db: Session,
    user: Faculty,
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[dict] = None,
    request: Optional[Request] = None
):
    """Log an audit entry"""
    if not settings.AUDIT_LOG_ENABLED:
        return
    
    try:
        import json
        
        audit_entry = AuditLog(
            user_id=user.id,
            user_name=user.name,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=json.dumps(details) if details else None,
            ip_address=request.client.host if request and request.client else None,
            user_agent=request.headers.get("user-agent") if request else None
        )
        db.add(audit_entry)
        db.commit()
        
        logger.info(f"AUDIT: {user.id} ({user.name}) performed {action} on {resource_type}:{resource_id}")
    except Exception as e:
        logger.error(f"Failed to log audit entry: {e}")
        # Don't fail the request if audit logging fails
        db.rollback()


def check_password_strength(password: str) -> tuple[bool, str]:
    """
    Validate password strength
    Returns: (is_valid, error_message)
    """
    if len(password) < settings.ADMIN_PASSWORD_MIN_LENGTH:
        return False, f"Password must be at least {settings.ADMIN_PASSWORD_MIN_LENGTH} characters"
    
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)
    
    if not (has_upper and has_lower and has_digit and has_special):
        return False, "Password must contain uppercase, lowercase, digit, and special character"
    
    return True, ""


def generate_secure_password() -> str:
    """Generate a secure random password"""
    import string
    import random
    
    # Ensure password has all required character types
    chars = []
    chars.append(random.choice(string.ascii_uppercase))
    chars.append(random.choice(string.ascii_lowercase))
    chars.append(random.choice(string.digits))
    chars.append(random.choice("!@#$%^&*()_+-="))
    
    # Fill remaining length with random characters
    all_chars = string.ascii_letters + string.digits + "!@#$%^&*()_+-="
    remaining_length = settings.ADMIN_PASSWORD_MIN_LENGTH - len(chars)
    chars.extend(random.choices(all_chars, k=remaining_length))
    
    # Shuffle to avoid predictable pattern
    random.shuffle(chars)
    return ''.join(chars)


def create_password_reset_token(db: Session, faculty_id: str) -> str:
    """Create a password reset token"""
    from .models import PasswordResetToken
    
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=24)
    
    reset_token = PasswordResetToken(
        faculty_id=faculty_id,
        token=token,
        expires_at=expires_at
    )
    db.add(reset_token)
    db.commit()
    
    return token


def validate_session_timeout(db: Session, session_id: str) -> bool:
    """Check if session has timed out"""
    session = db.query(SessionToken).filter_by(session_id=session_id).first()
    
    if not session or session.invalidated:
        return False
    
    now = datetime.utcnow()
    
    # Check absolute timeout
    if now > session.expires_at:
        session.invalidated = True
        session.invalidated_at = now
        db.commit()
        return False
    
    # Check inactivity timeout
    inactivity_timeout = timedelta(minutes=settings.SESSION_TIMEOUT_MINUTES)
    if now - session.last_activity > inactivity_timeout:
        session.invalidated = True
        session.invalidated_at = now
        db.commit()
        return False
    
    # Update last activity
    session.last_activity = now
    db.commit()
    
    return True


class SecurityMiddleware:
    """Middleware for additional security checks"""
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        request = Request(scope, receive)
        
        # Add security headers
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                
                # Security headers
                headers[b"x-content-type-options"] = b"nosniff"
                headers[b"x-frame-options"] = b"DENY"
                headers[b"x-xss-protection"] = b"1; mode=block"
                headers[b"strict-transport-security"] = b"max-age=31536000; includeSubDomains"
                
                message["headers"] = list(headers.items())
            
            await send(message)
        
        await self.app(scope, receive, send_wrapper)
