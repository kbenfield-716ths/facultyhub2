# backend/routes/admin_auth.py
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta

from ..models import SessionLocal, Faculty, PasswordResetToken
from ..auth import hash_password, verify_password, get_current_user, require_admin
from ..security import (
    log_audit, check_password_strength, generate_secure_password,
    create_password_reset_token, strict_limiter
)
from ..config import settings
from ..email_service import send_password_reset_email
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/auth", tags=["admin-auth"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


class SetPasswordRequest(BaseModel):
    new_password: str


@router.post("/change-password")
async def change_password(
    request: Request,
    payload: PasswordChangeRequest,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Change password for currently logged-in user.
    Requires current password verification.
    """
    await strict_limiter(request)
    
    # Verify current password
    if not verify_password(payload.current_password, current_user.password_hash):
        log_audit(db, current_user, "PASSWORD_CHANGE_FAILED", details={"reason": "incorrect_current_password"}, request=request)
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    # Validate new password strength
    is_valid, error_msg = check_password_strength(payload.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    # Check if new password is same as old
    if verify_password(payload.new_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="New password must be different from current password")
    
    # Update password
    current_user.password_hash = hash_password(payload.new_password)
    current_user.password_changed = True
    current_user.password_last_changed = datetime.utcnow()
    current_user.password_reset_required = False
    
    db.commit()
    
    log_audit(db, current_user, "PASSWORD_CHANGED", request=request)
    logger.info(f"Password changed for user {current_user.id}")
    
    return {"status": "ok", "message": "Password changed successfully"}


@router.post("/set-password")
async def set_initial_password(
    request: Request,
    payload: SetPasswordRequest,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Set initial password for users who haven't changed from default.
    Does not require current password if password_changed=False.
    """
    await strict_limiter(request)
    
    # Only allow if user hasn't changed password yet
    if current_user.password_changed:
        raise HTTPException(
            status_code=400,
            detail="Password already set. Use change-password endpoint instead."
        )
    
    # Validate new password strength
    is_valid, error_msg = check_password_strength(payload.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    # Update password
    current_user.password_hash = hash_password(payload.new_password)
    current_user.password_changed = True
    current_user.password_last_changed = datetime.utcnow()
    current_user.password_reset_required = False
    
    db.commit()
    
    log_audit(db, current_user, "INITIAL_PASSWORD_SET", request=request)
    logger.info(f"Initial password set for user {current_user.id}")
    
    return {"status": "ok", "message": "Password set successfully"}


@router.post("/request-password-reset")
async def request_password_reset(
    request: Request,
    payload: PasswordResetRequest,
    db: Session = Depends(get_db)
):
    """
    Request a password reset link via email.
    Always returns success to prevent email enumeration.
    """
    await strict_limiter(request)
    
    faculty = db.query(Faculty).filter_by(email=payload.email, active=True).first()
    
    if faculty:
        try:
            # Create reset token
            token = create_password_reset_token(db, faculty.id)
            
            # Send email
            send_password_reset_email(
                faculty_name=faculty.name,
                faculty_email=faculty.email,
                reset_token=token
            )
            
            logger.info(f"Password reset requested for {faculty.email}")
        except Exception as e:
            logger.error(f"Failed to send password reset email: {e}")
            # Don't reveal failure to user
    
    # Always return success to prevent email enumeration
    return {
        "status": "ok",
        "message": "If an account exists with that email, a password reset link has been sent."
    }


@router.post("/reset-password")
async def reset_password(
    request: Request,
    payload: PasswordResetConfirm,
    db: Session = Depends(get_db)
):
    """
    Reset password using a valid reset token.
    """
    await strict_limiter(request)
    
    # Find and validate token
    reset_token = db.query(PasswordResetToken).filter_by(
        token=payload.token,
        used=False
    ).first()
    
    if not reset_token:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    
    if datetime.utcnow() > reset_token.expires_at:
        raise HTTPException(status_code=400, detail="Reset token has expired")
    
    # Get faculty
    faculty = db.query(Faculty).filter_by(id=reset_token.faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=400, detail="Invalid reset token")
    
    # Validate new password
    is_valid, error_msg = check_password_strength(payload.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    # Update password
    faculty.password_hash = hash_password(payload.new_password)
    faculty.password_changed = True
    faculty.password_last_changed = datetime.utcnow()
    faculty.password_reset_required = False
    faculty.failed_login_attempts = 0
    faculty.account_locked_until = None
    
    # Mark token as used
    reset_token.used = True
    reset_token.used_at = datetime.utcnow()
    
    db.commit()
    
    log_audit(db, faculty, "PASSWORD_RESET_COMPLETED", request=request)
    logger.info(f"Password reset completed for {faculty.id}")
    
    return {"status": "ok", "message": "Password reset successfully"}


@router.post("/admin/force-password-reset/{faculty_id}")
async def admin_force_password_reset(
    request: Request,
    faculty_id: str,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to force a user to reset their password on next login.
    """
    faculty = db.query(Faculty).filter_by(id=faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")
    
    faculty.password_reset_required = True
    db.commit()
    
    log_audit(
        db, admin_user, "ADMIN_FORCE_PASSWORD_RESET",
        resource_type="Faculty", resource_id=faculty_id,
        request=request
    )
    
    return {"status": "ok", "message": f"Password reset required for {faculty.name}"}


@router.get("/check-password-status")
async def check_password_status(
    current_user: Faculty = Depends(get_current_user)
):
    """
    Check if user needs to set/change password.
    """
    return {
        "needs_password_change": not current_user.password_changed,
        "password_reset_required": current_user.password_reset_required,
        "password_last_changed": current_user.password_last_changed.isoformat() if current_user.password_last_changed else None
    }
