# backend/routes/admin_users.py
"""
Admin routes for user management operations.
Provides web-based tools for searching, managing, and troubleshooting faculty accounts.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, text
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
import bcrypt

from backend.models import (
    get_db, Faculty, SessionToken, PasswordResetToken,
    AuditLog, UnavailabilityRequest, ServiceWeekAssignment,
    Signup, Assignment, Message, MessageReaction
)
from backend.auth import require_admin, hash_password

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])

# Default password for resets
DEFAULT_PASSWORD = "PCCM2025!"


# ===== REQUEST/RESPONSE MODELS =====

class UserSearchResponse(BaseModel):
    id: str
    name: str
    email: str
    active: bool
    is_admin: bool
    registered: bool
    password_changed: bool
    password_reset_required: bool
    failed_login_attempts: int
    account_locked_until: Optional[str] = None
    last_login_at: Optional[str] = None
    last_login_ip: Optional[str] = None
    password_last_changed: Optional[str] = None
    moonlighter: bool
    extra_config: dict = {}


class ResetPasswordRequest(BaseModel):
    faculty_id: str


class UnlockAccountRequest(BaseModel):
    faculty_id: str


class ChangeUsernameRequest(BaseModel):
    old_id: str
    new_id: str


class ToggleAdminRequest(BaseModel):
    faculty_id: str


class ToggleActiveRequest(BaseModel):
    faculty_id: str


class DatabaseQueryRequest(BaseModel):
    query: str


# ===== SEARCH ENDPOINTS =====

@router.get("/search", response_model=List[UserSearchResponse])
async def search_users(
    query: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """
    Search for users by ID, name, or email.
    If no query provided, returns all users.
    """

    if not query:
        # Return all users
        users = db.query(Faculty).order_by(Faculty.name).all()
    else:
        # Search by ID, name, or email
        search_term = f"%{query}%"
        users = db.query(Faculty).filter(
            or_(
                Faculty.id.ilike(search_term),
                Faculty.name.ilike(search_term),
                Faculty.email.ilike(search_term)
            )
        ).order_by(Faculty.name).all()

    return [_faculty_to_response(user) for user in users]


@router.get("/{faculty_id}", response_model=UserSearchResponse)
async def get_user_details(
    faculty_id: str,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """Get detailed information about a specific user"""

    user = db.query(Faculty).filter(Faculty.id == faculty_id.upper()).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return _faculty_to_response(user)


# ===== MANAGEMENT ENDPOINTS =====

@router.post("/reset-password")
async def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """Reset a user's password to the default"""

    faculty = db.query(Faculty).filter(Faculty.id == request.faculty_id.upper()).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="User not found")

    # Generate new password hash
    new_hash = hash_password(DEFAULT_PASSWORD)

    # Update password and reset security fields
    faculty.password_hash = new_hash
    faculty.password_changed = False
    faculty.password_reset_required = False
    faculty.failed_login_attempts = 0
    faculty.account_locked_until = None
    faculty.password_last_changed = datetime.utcnow()

    # Log the action
    _log_admin_action(
        db, current_user.id, current_user.name,
        "password_reset", "faculty", faculty.id,
        f"Reset password for {faculty.name}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Password reset to default for {faculty.name}",
        "faculty_id": faculty.id,
        "default_password": DEFAULT_PASSWORD
    }


@router.post("/unlock-account")
async def unlock_account(
    request: UnlockAccountRequest,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """Unlock a locked account and reset failed login attempts"""

    faculty = db.query(Faculty).filter(Faculty.id == request.faculty_id.upper()).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="User not found")

    # Reset security fields
    faculty.failed_login_attempts = 0
    faculty.account_locked_until = None

    # Log the action
    _log_admin_action(
        db, current_user.id, current_user.name,
        "unlock_account", "faculty", faculty.id,
        f"Unlocked account for {faculty.name}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Account unlocked for {faculty.name}",
        "faculty_id": faculty.id
    }


@router.post("/change-username")
async def change_username(
    request: ChangeUsernameRequest,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """
    Change a user's faculty ID (username).
    This updates the primary key across all related tables.
    """

    old_id = request.old_id.upper()
    new_id = request.new_id.upper()

    # Check if old user exists
    old_user = db.query(Faculty).filter(Faculty.id == old_id).first()
    if not old_user:
        raise HTTPException(status_code=404, detail=f"User {old_id} not found")

    # Check if new ID already exists
    new_user = db.query(Faculty).filter(Faculty.id == new_id).first()
    if new_user:
        raise HTTPException(status_code=400, detail=f"User {new_id} already exists")

    # Disable foreign key constraints
    db.execute(text("PRAGMA foreign_keys = OFF"))

    try:
        # Tables with faculty_id foreign keys that need updating
        updates = []

        # Update signups
        result = db.execute(
            text("UPDATE signups SET provider_id = :new_id WHERE provider_id = :old_id"),
            {"new_id": new_id, "old_id": old_id}
        )
        if result.rowcount > 0:
            updates.append(f"signups.provider_id: {result.rowcount} records")

        # Update assignments
        result = db.execute(
            text("UPDATE assignments SET provider_id = :new_id WHERE provider_id = :old_id"),
            {"new_id": new_id, "old_id": old_id}
        )
        if result.rowcount > 0:
            updates.append(f"assignments.provider_id: {result.rowcount} records")

        # Update unavailability_requests
        result = db.execute(
            text("UPDATE unavailability_requests SET faculty_id = :new_id WHERE faculty_id = :old_id"),
            {"new_id": new_id, "old_id": old_id}
        )
        if result.rowcount > 0:
            updates.append(f"unavailability_requests.faculty_id: {result.rowcount} records")

        # Update service_week_assignments
        result = db.execute(
            text("UPDATE service_week_assignments SET faculty_id = :new_id WHERE faculty_id = :old_id"),
            {"new_id": new_id, "old_id": old_id}
        )
        if result.rowcount > 0:
            updates.append(f"service_week_assignments.faculty_id: {result.rowcount} records")

        result = db.execute(
            text("UPDATE service_week_assignments SET created_by = :new_id WHERE created_by = :old_id"),
            {"new_id": new_id, "old_id": old_id}
        )
        if result.rowcount > 0:
            updates.append(f"service_week_assignments.created_by: {result.rowcount} records")

        # Update messages
        result = db.execute(
            text("UPDATE messages SET author_id = :new_id WHERE author_id = :old_id"),
            {"new_id": new_id, "old_id": old_id}
        )
        if result.rowcount > 0:
            updates.append(f"messages.author_id: {result.rowcount} records")

        # Update message_reactions
        result = db.execute(
            text("UPDATE message_reactions SET faculty_id = :new_id WHERE faculty_id = :old_id"),
            {"new_id": new_id, "old_id": old_id}
        )
        if result.rowcount > 0:
            updates.append(f"message_reactions.faculty_id: {result.rowcount} records")

        # Update message_read_status
        result = db.execute(
            text("UPDATE message_read_status SET faculty_id = :new_id WHERE faculty_id = :old_id"),
            {"new_id": new_id, "old_id": old_id}
        )
        if result.rowcount > 0:
            updates.append(f"message_read_status.faculty_id: {result.rowcount} records")

        # Update session_tokens
        result = db.execute(
            text("UPDATE session_tokens SET faculty_id = :new_id WHERE faculty_id = :old_id"),
            {"new_id": new_id, "old_id": old_id}
        )
        if result.rowcount > 0:
            updates.append(f"session_tokens.faculty_id: {result.rowcount} records")

        # Update password_reset_tokens
        result = db.execute(
            text("UPDATE password_reset_tokens SET faculty_id = :new_id WHERE faculty_id = :old_id"),
            {"new_id": new_id, "old_id": old_id}
        )
        if result.rowcount > 0:
            updates.append(f"password_reset_tokens.faculty_id: {result.rowcount} records")

        # Update audit_logs
        result = db.execute(
            text("UPDATE audit_logs SET user_id = :new_id WHERE user_id = :old_id"),
            {"new_id": new_id, "old_id": old_id}
        )
        if result.rowcount > 0:
            updates.append(f"audit_logs.user_id: {result.rowcount} records")

        # Update night-scheduling tables (blocked nights, preferences, quotas,
        # assignments, and assigned_by audit trail on assignments)
        result = db.execute(
            text("UPDATE blocked_nights SET provider_id = :new_id WHERE provider_id = :old_id"),
            {"new_id": new_id, "old_id": old_id}
        )
        if result.rowcount > 0:
            updates.append(f"blocked_nights.provider_id: {result.rowcount} records")

        result = db.execute(
            text("UPDATE night_preferences SET provider_id = :new_id WHERE provider_id = :old_id"),
            {"new_id": new_id, "old_id": old_id}
        )
        if result.rowcount > 0:
            updates.append(f"night_preferences.provider_id: {result.rowcount} records")

        result = db.execute(
            text("UPDATE provider_night_quotas SET provider_id = :new_id WHERE provider_id = :old_id"),
            {"new_id": new_id, "old_id": old_id}
        )
        if result.rowcount > 0:
            updates.append(f"provider_night_quotas.provider_id: {result.rowcount} records")

        result = db.execute(
            text("UPDATE period_assignments SET provider_id = :new_id WHERE provider_id = :old_id"),
            {"new_id": new_id, "old_id": old_id}
        )
        if result.rowcount > 0:
            updates.append(f"period_assignments.provider_id: {result.rowcount} records")

        result = db.execute(
            text("UPDATE period_assignments SET assigned_by = :new_id WHERE assigned_by = :old_id"),
            {"new_id": new_id, "old_id": old_id}
        )
        if result.rowcount > 0:
            updates.append(f"period_assignments.assigned_by: {result.rowcount} records")

        # Update the primary key in faculty table
        db.execute(
            text("UPDATE faculty SET id = :new_id WHERE id = :old_id"),
            {"new_id": new_id, "old_id": old_id}
        )

        # Log the action
        _log_admin_action(
            db, current_user.id, current_user.name,
            "change_username", "faculty", new_id,
            f"Changed username from {old_id} to {new_id}. Updated: {', '.join(updates)}"
        )

        db.commit()

        # Re-enable foreign key constraints
        db.execute(text("PRAGMA foreign_keys = ON"))

        return {
            "success": True,
            "message": f"Username changed from {old_id} to {new_id}",
            "old_id": old_id,
            "new_id": new_id,
            "updates": updates
        }

    except Exception as e:
        db.rollback()
        db.execute(text("PRAGMA foreign_keys = ON"))
        raise HTTPException(status_code=500, detail=f"Failed to change username: {str(e)}")


@router.post("/toggle-admin")
async def toggle_admin_status(
    request: ToggleAdminRequest,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """Toggle admin status for a user"""

    faculty = db.query(Faculty).filter(Faculty.id == request.faculty_id.upper()).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="User not found")

    # Toggle admin status
    new_status = not faculty.is_admin
    faculty.is_admin = new_status

    # Log the action
    _log_admin_action(
        db, current_user.id, current_user.name,
        "toggle_admin", "faculty", faculty.id,
        f"{'Granted' if new_status else 'Revoked'} admin privileges for {faculty.name}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Admin status {'granted' if new_status else 'revoked'} for {faculty.name}",
        "faculty_id": faculty.id,
        "is_admin": new_status
    }


@router.post("/toggle-active")
async def toggle_active_status(
    request: ToggleActiveRequest,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """Toggle active status for a user"""

    faculty = db.query(Faculty).filter(Faculty.id == request.faculty_id.upper()).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="User not found")

    # Toggle active status
    new_status = not faculty.active
    faculty.active = new_status

    # Log the action
    _log_admin_action(
        db, current_user.id, current_user.name,
        "toggle_active", "faculty", faculty.id,
        f"{'Activated' if new_status else 'Deactivated'} account for {faculty.name}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Account {'activated' if new_status else 'deactivated'} for {faculty.name}",
        "faculty_id": faculty.id,
        "active": new_status
    }


# ===== DATABASE QUERY ENDPOINT =====

@router.post("/database-query")
async def execute_database_query(
    request: DatabaseQueryRequest,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """
    Execute a read-only database query.
    Only SELECT queries are allowed for safety.
    """

    query = request.query.strip()

    # Security check: only allow SELECT queries
    query_upper = query.upper()
    dangerous_keywords = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'CREATE', 'TRUNCATE', 'REPLACE']

    for keyword in dangerous_keywords:
        if keyword in query_upper:
            raise HTTPException(
                status_code=403,
                detail=f"{keyword} operations not allowed. Only SELECT queries permitted."
            )

    try:
        # Execute the query
        result = db.execute(text(query))

        # Get column names
        if result.returns_rows:
            columns = list(result.keys())
            rows = []

            for row in result:
                # Convert row to dict
                row_dict = {}
                for i, col in enumerate(columns):
                    value = row[i]
                    # Convert non-serializable types
                    if isinstance(value, datetime):
                        value = value.isoformat()
                    elif value is None:
                        value = None
                    else:
                        value = str(value)
                    row_dict[col] = value
                rows.append(row_dict)

            # Log the query
            _log_admin_action(
                db, current_user.id, current_user.name,
                "database_query", "database", "query",
                f"Executed query: {query[:100]}..."
            )

            return {
                "success": True,
                "columns": columns,
                "rows": rows,
                "row_count": len(rows)
            }
        else:
            return {
                "success": True,
                "message": "Query executed successfully (no results returned)",
                "columns": [],
                "rows": [],
                "row_count": 0
            }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Query error: {str(e)}")


# ===== UTILITY FUNCTIONS =====

def _faculty_to_response(faculty: Faculty) -> UserSearchResponse:
    """Convert Faculty model to response"""
    return UserSearchResponse(
        id=faculty.id,
        name=faculty.name,
        email=faculty.email,
        active=faculty.active,
        is_admin=faculty.is_admin,
        registered=faculty.registered,
        password_changed=faculty.password_changed,
        password_reset_required=faculty.password_reset_required or False,
        failed_login_attempts=faculty.failed_login_attempts or 0,
        account_locked_until=faculty.account_locked_until.isoformat() if faculty.account_locked_until else None,
        last_login_at=faculty.last_login_at.isoformat() if faculty.last_login_at else None,
        last_login_ip=faculty.last_login_ip,
        password_last_changed=faculty.password_last_changed.isoformat() if faculty.password_last_changed else None,
        moonlighter=faculty.moonlighter,
        extra_config=__import__("json").loads(faculty.extra_config or "{}"),
    )


def _log_admin_action(
    db: Session,
    user_id: str,
    user_name: str,
    action: str,
    resource_type: str,
    resource_id: str,
    details: str
):
    """Log an admin action to the audit log"""
    log_entry = AuditLog(
        user_id=user_id,
        user_name=user_name,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        timestamp=datetime.utcnow()
    )
    db.add(log_entry)
