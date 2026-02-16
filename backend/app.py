# backend/app.py
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
from datetime import date, datetime
from pathlib import Path
import csv
import io
import logging

from sqlalchemy.orm import Session
from sqlalchemy import delete
from .auth import get_current_user, hash_password

from .models import (
    SessionLocal, init_db, get_db,
    Month, Shift, Signup, Assignment, Faculty, AuditLog
)
from .optimizer_bridge import run_optimizer_for_month
from fastapi.middleware.gzip import GZipMiddleware
from .routes.admin_faculty import router as admin_faculty_router
from .routes.admin_service import router as admin_service_router
from .routes.admin_users import router as admin_users_router
from .routes.auth import router as auth_router
from .routes.service_requests import router as service_requests_router
from .routes.service_weeks import router as service_weeks_router
from .routes.schedule_routes import router as schedule_router
from .routes.messages import router as messages_router
from backend.email_service import send_irpa_confirmation
from .routes import knowledge_base
from .routes import draft
from .models import Base, engine
from .config import settings
from .security import SecurityMiddleware, standard_limiter, log_audit, generate_secure_password
from .auth import optional_require_admin, require_admin
from .routes.admin_auth import router as admin_auth_router
from backend.routes.admin_data_management import router as data_management_router
from backend.routes.service_week_overrides import router as service_week_overrides_router

logger = logging.getLogger(__name__)

# Create tables
Base.metadata.create_all(bind=engine)

# ---------- App Initialization -----------
app = FastAPI()

# Add middleware in correct order
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(SecurityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),  # Dynamic based on config
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Health Check -----------
@app.get("/health")
async def health_check():
    """Health check endpoint for Fly.io monitoring"""
    return {"status": "healthy"}

# ---------- Include Routers FIRST - before catch-all routes -----------
app.include_router(auth_router)
app.include_router(admin_auth_router)  # New admin auth routes
app.include_router(admin_faculty_router)
app.include_router(admin_service_router)
app.include_router(admin_users_router)  # User management routes
app.include_router(service_requests_router)
app.include_router(service_weeks_router)
app.include_router(schedule_router)
app.include_router(messages_router)
app.include_router(knowledge_base.router)
app.include_router(draft.router)
app.include_router(data_management_router)
app.include_router(service_week_overrides_router)

# ---------- Static File Setup -----------
STATIC_DIR = Path(__file__).resolve().parent.parent
BACKEND_STATIC_DIR = Path(__file__).resolve().parent / "static"

if (STATIC_DIR / "icons").exists():
    app.mount("/icons", StaticFiles(directory=str(STATIC_DIR / "icons")), name="icons")

# Serve entire admin directory (includes modules and index.html)
if (STATIC_DIR / "admin").exists():
    app.mount("/admin", StaticFiles(directory=str(STATIC_DIR / "admin"), html=True), name="admin")

# ---------- Pydantic Schemas ----------
class SignupPayload(BaseModel):
    provider_id: str
    provider_name: str
    month: str
    desired_nights: int
    dates: List[date]
    locked_dates: List[date] = []

class SignupOut(BaseModel):
    provider_id: str
    provider_name: str
    date: date
    month: str
    desired_nights: int
    locked: bool

    class Config:
        from_attributes = True

class ProviderOut(BaseModel):
    id: str
    name: str
    email: Optional[str] = None

    class Config:
        from_attributes = True

class ProviderCreate(BaseModel):
    id: str
    name: str
    email: Optional[str] = None

class ProviderUpdate(BaseModel):
    name: str
    email: Optional[str] = None

class AssignmentOut(BaseModel):
    provider_id: str
    provider_name: str
    date: date
    month: str

    class Config:
        from_attributes = True

class FeedbackSubmission(BaseModel):
    feedback_type: str
    message: str
    page_url: Optional[str] = None

# ---------- Startup Event ----------
@app.on_event("startup")
def startup_event():
    """Initialize database and seed data on startup."""
    init_db()
    
    # Seed message boards
    from .models import seed_message_boards
    db = SessionLocal()
    try:
        seed_message_boards(db)
        print("[Startup] Message boards seeded")
    except Exception as e:
        print(f"[Startup] Message boards: {e}")
    finally:
        db.close()
    
    # Create default admin user with secure handling
    db = SessionLocal()
    try:
        admin_count = db.query(Faculty).filter_by(is_admin=True).count()
        if admin_count == 0:
            # Generate secure password or use env var
            if settings.allows_default_admin() and settings.ADMIN_DEFAULT_PASSWORD:
                admin_password = settings.ADMIN_DEFAULT_PASSWORD
                print("[Startup] Using ADMIN_DEFAULT_PASSWORD from environment")
            else:
                admin_password = generate_secure_password()
                print("=" * 80)
                print("[Startup] GENERATED ADMIN PASSWORD (SAVE THIS IMMEDIATELY):")
                print(f"  Username: ADMIN")
                print(f"  Password: {admin_password}")
                print("=" * 80)
                print("This password will not be shown again!")
                print("Admin user must change password on first login.")
                print("=" * 80)
                
                # Optionally write to secure file
                try:
                    with open(".admin_initial_password", "w") as f:
                        f.write(f"Username: ADMIN\nPassword: {admin_password}\nGenerated: {datetime.utcnow()}\n")
                    print("[Startup] Password also saved to .admin_initial_password (delete after use)")
                except Exception as e:
                    print(f"[Startup] Could not save password to file: {e}")
            
            admin = Faculty(
                id="ADMIN",
                name="Administrator",
                email="admin@example.com",  # TODO: Change this
                rank="full",
                clinical_effort_pct=0,
                base_points=0,
                is_admin=True,
                password_hash=hash_password(admin_password),
                password_changed=False,  # Force password change
                password_reset_required=True,
                registered=True,
                active=True
            )
            db.add(admin)
            db.commit()
            
            if not settings.allows_default_admin():
                print("[Startup] Default admin login disabled in strict mode")
                print("[Startup] Admin must use password reset to set secure password")
    except Exception as e:
        print(f"[Startup] Error creating admin user: {e}")
        db.rollback()
    finally:
        db.close()

    # Seed unavailability data from CSV (if weeks exist)
    try:
        from .seed_unavailability import seed_all_historic_data
        seed_all_historic_data()
    except Exception as e:
        print(f"[Startup] Note: {e}")


# ========================================
# API ROUTES - MUST COME BEFORE STATIC FILE ROUTES
# ========================================

# ---------- Signup Endpoint ----------
@app.post("/api/signup")
async def save_signup(
    request: Request,
    payload: SignupPayload,
    db: Session = Depends(get_db)
):
    """Save moonlighting signup for a provider."""
    await standard_limiter(request)

    # Get faculty member (provider)
    faculty = db.query(Faculty).filter(Faculty.id == payload.provider_id).first()
    if not faculty:
        raise HTTPException(404, f"Faculty member '{payload.provider_id}' not found")

    # Update name if provided
    if payload.provider_name and faculty.name != payload.provider_name:
        faculty.name = payload.provider_name

    # Ensure Month row exists
    year, month_num = map(int, payload.month.split("-"))
    month_row = (
        db.query(Month)
        .filter(Month.year == year, Month.month == month_num)
        .first()
    )
    if not month_row:
        month_row = Month(year=year, month=month_num)
        db.add(month_row)
        db.flush()

    # Ensure shifts exist for the selected dates
    existing_shifts = {
        s.date: s for s in db.query(Shift).filter(Shift.month_id == month_row.id)
    }

    selected_dates = set(payload.dates) | set(payload.locked_dates)

    for d in selected_dates:
        if d not in existing_shifts:
            s = Shift(month_id=month_row.id, date=d, slots=1)
            db.add(s)
            db.flush()
            existing_shifts[d] = s

    # Clear old signups for this provider in this month
    shift_ids = [s.id for s in existing_shifts.values()]
    db.query(Signup).filter(
        Signup.provider_id == payload.provider_id,
        Signup.shift_id.in_(shift_ids)
    ).delete(synchronize_session=False)

    # Write new signups
    locked_set = set(payload.locked_dates)
    for d in payload.dates:
        su = Signup(
            provider_id=payload.provider_id,
            desired_nights=payload.desired_nights,
            locked=d in locked_set,
            shift_id=existing_shifts[d].id,
        )
        db.add(su)

    db.commit()

    # Refresh faculty to get updated data
    db.refresh(faculty)

    # Send confirmation email (non-blocking)
    try:
        date_strings = [d.isoformat() for d in sorted(payload.dates)]

        if month_num >= 7:
            academic_year = f"{year}-{year+1}"
        else:
            academic_year = f"{year-1}-{year}"

        if faculty.email:
            send_irpa_confirmation(
                faculty_name=faculty.name,
                faculty_email=faculty.email,
                selected_dates=date_strings,
                academic_year=academic_year
            )
            logger.info(f"IRPA confirmation email sent to {faculty.email}")
        else:
            logger.warning(f"No email on file for faculty {faculty.name} ({payload.provider_id})")
    except Exception as e:
        logger.error(f"Failed to send IRPA confirmation email: {e}")
    
    return {"status": "ok"}


# ---------- Admin: List Signups ----------
@app.get("/api/admin/signups", response_model=List[SignupOut])
async def list_signups(
    request: Request,
    month: Optional[str] = None,
    current_user: Faculty = Depends(optional_require_admin),
    db: Session = Depends(get_db),
):
    """Return one row per provider-date signup."""
    await standard_limiter(request)

    q = (
        db.query(
            Signup.provider_id,
            Faculty.name.label("provider_name"),
            Shift.date.label("date"),
            Month.year.label("year"),
            Month.month.label("month_num"),
            Signup.desired_nights,
            Signup.locked,
        )
        .join(Faculty, Signup.provider_id == Faculty.id)
        .join(Shift, Signup.shift_id == Shift.id)
        .join(Month, Shift.month_id == Month.id)
    )

    if month:
        year, mnum = map(int, month.split("-"))
        q = q.filter(Month.year == year, Month.month == mnum)

    rows = q.order_by(Faculty.name, Shift.date).all()

    result: List[SignupOut] = []
    for r in rows:
        month_str = f"{r.year:04d}-{r.month_num:02d}"
        result.append(
            SignupOut(
                provider_id=r.provider_id,
                provider_name=r.provider_name,
                date=r.date,
                month=month_str,
                desired_nights=r.desired_nights,
                locked=bool(r.locked),
            )
        )
    
    if settings.AUDIT_LOG_ENABLED and current_user:
        log_audit(db, current_user, "VIEW_SIGNUPS", details={"month": month}, request=request)
    
    return result


# ---------- Admin: List Assignments ----------
@app.get("/api/admin/assignments", response_model=List[AssignmentOut])
async def list_assignments(
    request: Request,
    month: Optional[str] = None,
    current_user: Faculty = Depends(optional_require_admin),
    db: Session = Depends(get_db),
):
    """Return the generated schedule (assignments) for a month."""
    await standard_limiter(request)

    q = (
        db.query(
            Assignment.provider_id,
            Faculty.name.label("provider_name"),
            Shift.date.label("date"),
            Month.year.label("year"),
            Month.month.label("month_num"),
        )
        .join(Faculty, Assignment.provider_id == Faculty.id)
        .join(Shift, Assignment.shift_id == Shift.id)
        .join(Month, Shift.month_id == Month.id)
    )

    if month:
        year, mnum = map(int, month.split("-"))
        q = q.filter(Month.year == year, Month.month == mnum)

    rows = q.order_by(Shift.date, Faculty.name).all()

    result: List[AssignmentOut] = []
    for r in rows:
        month_str = f"{r.year:04d}-{r.month_num:02d}"
        result.append(
            AssignmentOut(
                provider_id=r.provider_id,
                provider_name=r.provider_name,
                date=r.date,
                month=month_str,
            )
        )
    
    if settings.AUDIT_LOG_ENABLED and current_user:
        log_audit(db, current_user, "VIEW_ASSIGNMENTS", details={"month": month}, request=request)
    
    return result


# ---------- Providers List ----------
@app.get("/api/providers", response_model=List[ProviderOut])
async def list_providers(request: Request, db: Session = Depends(get_db)):
    """Get all active faculty who are moonlighters."""
    await standard_limiter(request)

    faculty = db.query(Faculty).filter(
        Faculty.active == True,
        Faculty.moonlighter == True
    ).order_by(Faculty.name).all()

    return [
        ProviderOut(id=f.id, name=f.name, email=f.email)
        for f in faculty
    ]


@app.post("/api/admin/providers")
async def create_provider(
    request: Request,
    provider: ProviderCreate,
    current_user: Faculty = Depends(optional_require_admin),
    db: Session = Depends(get_db)
):
    """Add a new faculty member as a moonlighter."""
    await standard_limiter(request)

    existing = db.query(Faculty).filter(Faculty.id == provider.id).first()
    if existing:
        existing.moonlighter = True
        if provider.email:
            existing.email = provider.email
        db.commit()
        return {"status": "updated", "id": existing.id}

    new_faculty = Faculty(
        id=provider.id,
        name=provider.name,
        email=provider.email or "",
        rank="assistant",
        clinical_effort_pct=100,
        base_points=0,
        moonlighter=True,
        active=True
    )
    db.add(new_faculty)
    db.commit()

    return {"status": "created", "id": new_faculty.id, "name": new_faculty.name}


# ---------- Admin: Clear Data ----------
@app.delete("/api/admin/clear_month")
async def clear_month_data(
    request: Request,
    month: str,
    current_user: Faculty = Depends(optional_require_admin),
    db: Session = Depends(get_db)
):
    """Clear all signups and assignments for a specific month."""
    await standard_limiter(request)
    
    # Parse and validate month format
    try:
        parts = month.split("-")
        if len(parts) != 2:
            raise ValueError("Invalid format")
        year = int(parts[0])
        month_num = int(parts[1])
        if month_num < 1 or month_num > 12:
            raise ValueError("Month must be between 1 and 12")
    except (ValueError, IndexError) as e:
        raise HTTPException(400, f"Invalid month format. Expected YYYY-MM (e.g., 2026-01), got: {month}")
    
    month_row = (
        db.query(Month)
        .filter(Month.year == year, Month.month == month_num)
        .first()
    )
    
    if not month_row:
        return {"status": "ok", "message": "No data found for this month"}
    
    # Get shift IDs first
    shift_ids = [s.id for s in month_row.shifts]
    
    if not shift_ids:
        db.delete(month_row)
        db.commit()
        return {"status": "ok", "message": f"Deleted empty month {month}"}
    
    # Use SQLAlchemy delete() to avoid StaleDataError
    assignment_count = db.execute(
        delete(Assignment).where(Assignment.shift_id.in_(shift_ids))
    ).rowcount
    
    signup_count = db.execute(
        delete(Signup).where(Signup.shift_id.in_(shift_ids))
    ).rowcount
    
    shift_count = db.execute(
        delete(Shift).where(Shift.month_id == month_row.id)
    ).rowcount
    
    db.delete(month_row)
    db.commit()
    
    if settings.AUDIT_LOG_ENABLED and current_user:
        log_audit(
            db, current_user, "CLEAR_MONTH",
            resource_type="Month", resource_id=month,
            details={
                "signups_deleted": signup_count,
                "assignments_deleted": assignment_count,
                "shifts_deleted": shift_count
            },
            request=request
        )
    
    return {
        "status": "ok",
        "message": f"Cleared month {month}: {signup_count} signups, {assignment_count} assignments, {shift_count} shifts"
    }


@app.delete("/api/admin/clear_all")
async def clear_all_data(
    request: Request,
    confirm: str,
    current_user: Faculty = Depends(require_admin),  # STRICT - always require auth
    db: Session = Depends(get_db)
):
    """Clear ALL data - DESTRUCTIVE OPERATION. Always requires authentication."""
    await standard_limiter(request)
    
    if confirm != "DELETE_ALL_DATA":
        raise HTTPException(400, "Confirmation string required: DELETE_ALL_DATA")
    
    # Count before deletion
    counts = {
        "assignments": db.query(Assignment).count(),
        "signups": db.query(Signup).count(),
        "shifts": db.query(Shift).count(),
        "months": db.query(Month).count()
    }
    
    # Delete
    db.query(Assignment).delete()
    db.query(Signup).delete()
    db.query(Shift).delete()
    db.query(Month).delete()
    db.commit()
    
    log_audit(
        db, current_user, "CLEAR_ALL_DATA",
        details=counts,
        request=request
    )
    
    logger.warning(f"ALL DATA CLEARED by {current_user.id} ({current_user.name})")
    
    return {
        "status": "ok",
        "message": f"Cleared all data: {counts['assignments']} assignments, {counts['signups']} signups, {counts['shifts']} shifts, {counts['months']} months"
    }


# ---------- Admin: Run Optimizer ----------
@app.post("/api/admin/run_optimizer")
async def run_optimizer_endpoint(
    request: Request,
    month: str,
    strategy: str = "balanced",
    night_slots: int = 1,
    current_user: Faculty = Depends(optional_require_admin),
    db: Session = Depends(get_db),
):
    """Run the scheduling optimizer for a given month."""
    await standard_limiter(request)
    
    try:
        year, month_num = map(int, month.split("-"))
        month_row = (
            db.query(Month)
            .filter(Month.year == year, Month.month == month_num)
            .first()
        )
        
        if not month_row:
            raise HTTPException(404, f"No signups found for month {month}")
        
        # Run optimizer
        assignments = run_optimizer_for_month(db, month_row, strategy, night_slots)
        
        # Clear existing assignments for this month
        shift_ids = [s.id for s in month_row.shifts]
        db.query(Assignment).filter(Assignment.shift_id.in_(shift_ids)).delete(synchronize_session=False)
        
        # Save new assignments
        for provider, shift in assignments:
            assignment = Assignment(provider_id=provider.id, shift_id=shift.id)
            db.add(assignment)
        
        db.commit()
        
        if settings.AUDIT_LOG_ENABLED and current_user:
            log_audit(
                db, current_user, "RUN_OPTIMIZER",
                details={
                    "month": month,
                    "strategy": strategy,
                    "assigned_shifts": len(assignments)
                },
                request=request
            )
        
        return {
            "status": "ok",
            "month": month,
            "assigned_shifts": len(assignments),
            "strategy": strategy
        }
    except Exception as e:
        logger.error(f"Optimizer error: {e}")
        raise HTTPException(500, f"Optimizer failed: {str(e)}")


# ---------- Admin: CSV Export ----------
@app.get("/api/admin/signups_csv", response_class=PlainTextResponse)
async def signups_csv(
    request: Request,
    month: str,
    current_user: Faculty = Depends(optional_require_admin),
    db: Session = Depends(get_db),
):
    """Export all signups for a given month as CSV."""
    await standard_limiter(request)

    year, mnum = map(int, month.split("-"))

    q = (
        db.query(
            Signup.provider_id,
            Faculty.name,
            Shift.date,
            Signup.desired_nights,
        )
        .join(Faculty, Signup.provider_id == Faculty.id)
        .join(Shift, Signup.shift_id == Shift.id)
        .join(Month, Shift.month_id == Month.id)
        .filter(Month.year == year, Month.month == mnum)
        .order_by(Faculty.name, Shift.date)
    )

    rows = q.all()
    
    from collections import defaultdict
    providers_data = defaultdict(lambda: {"dates": [], "desired_nights": 0, "name": ""})
    
    for r in rows:
        providers_data[r.provider_id]["name"] = r.name
        providers_data[r.provider_id]["dates"].append(r.date.isoformat())
        providers_data[r.provider_id]["desired_nights"] = r.desired_nights

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["faculty_id", "name", "desired_nights", "requested_dates", "priority"])

    for faculty_id, data in sorted(providers_data.items()):
        dates_str = ",".join(data["dates"])
        writer.writerow([
            faculty_id,
            data["name"],
            data["desired_nights"],
            dates_str,
            2
        ])

    csv_text = output.getvalue()
    headers = {
        "Content-Disposition": f'attachment; filename="moonlighter_template_{month}.csv"'
    }
    
    if settings.AUDIT_LOG_ENABLED and current_user:
        log_audit(db, current_user, "EXPORT_SIGNUPS_CSV", details={"month": month}, request=request)
    
    return PlainTextResponse(csv_text, headers=headers)


# ---------- Admin: Audit Logs ----------
@app.get("/api/admin/audit-logs")
async def get_audit_logs(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """View audit logs (admin only)."""
    await standard_limiter(request)
    
    if not settings.AUDIT_LOG_ENABLED:
        return {"logs": [], "message": "Audit logging is disabled"}
    
    query = db.query(AuditLog)
    
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)
    if start_date:
        query = query.filter(AuditLog.timestamp >= start_date)
    if end_date:
        query = query.filter(AuditLog.timestamp <= end_date)
    
    total = query.count()
    logs = query.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit).all()
    
    return {
        "logs": [
            {
                "id": log.id,
                "timestamp": log.timestamp.isoformat(),
                "user_id": log.user_id,
                "user_name": log.user_name,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "details": log.details,
                "ip_address": log.ip_address
            }
            for log in logs
        ],
        "total": total,
        "limit": limit,
        "offset": offset
    }


# ---------- Feedback ----------
@app.post("/api/feedback")
async def submit_feedback(
    request: Request,
    feedback: FeedbackSubmission,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit user feedback"""
    from .email_service import send_feedback_email
    
    await standard_limiter(request)
    
    try:
        success = send_feedback_email(
            user_name=current_user.name,
            user_email=current_user.email,
            feedback_type=feedback.feedback_type,
            message=feedback.message,
            page_url=feedback.page_url
        )
        
        if success:
            return {"status": "ok", "message": "Feedback sent successfully"}
        else:
            raise HTTPException(500, "Failed to send feedback email")
    except Exception as e:
        logger.error(f"Feedback submission error: {e}")
        raise HTTPException(500, f"Error: {str(e)}")


# ========================================
# STATIC FILE ROUTES - MUST COME AFTER API ROUTES
# ========================================

@app.get("/")
async def serve_index():
    """Serve the main index.html"""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"status": "ok", "message": "API running"}


@app.get("/favicon.ico")
async def serve_favicon_ico():
    favicon_path = STATIC_DIR / "favicon.ico"
    if favicon_path.exists():
        return FileResponse(favicon_path)
    svg_path = STATIC_DIR / "favicon.svg"
    if svg_path.exists():
        return FileResponse(svg_path, media_type="image/svg+xml")
    return {"error": "favicon not found"}


@app.get("/favicon.svg")
async def serve_favicon_svg():
    favicon_path = STATIC_DIR / "favicon.svg"
    if favicon_path.exists():
        response = FileResponse(favicon_path, media_type="image/svg+xml")
        response.headers["Cache-Control"] = "public, max-age=86400"
        return response 
    return {"error": "favicon.svg not found"}


@app.get("/manifest.json")
async def serve_manifest():
    manifest_path = STATIC_DIR / "manifest.json"
    if manifest_path.exists():
        response = FileResponse(manifest_path)
        response.headers["Cache-Control"] = "public, max-age=3600"
        return response
    return {"error": "manifest.json not found"}


@app.get("/service-worker.js")
async def serve_service_worker():
    """Serve the service worker file"""
    sw_path = STATIC_DIR / "service-worker.js"
    if sw_path.exists():
        response = FileResponse(sw_path, media_type="application/javascript")
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Service-Worker-Allowed"] = "/"
        return response
    return {"error": "service-worker.js not found"}

@app.get("/{filename}.html")
async def serve_html_file(filename: str):
    """Serve any HTML file from root directory"""
    html_path = STATIC_DIR / f"{filename}.html"
    if html_path.exists():
        response = FileResponse(html_path)
        response.headers["Cache-Control"] = "public, max-age=3600"
        return response
    
    for file in STATIC_DIR.glob("*.html"):
        if file.stem.lower() == filename.lower():
            response = FileResponse(file)
            response.headers["Cache-Control"] = "public, max-age=3600"
            return response
    
    for file in STATIC_DIR.glob("*.Html"):
        if file.stem.lower() == filename.lower():
            response = FileResponse(file)
            response.headers["Cache-Control"] = "public, max-age=3600"
            return response
    
    backend_html_path = BACKEND_STATIC_DIR / f"{filename}.html"
    if backend_html_path.exists():
        response = FileResponse(backend_html_path)
        response.headers["Cache-Control"] = "public, max-age=3600"
        return response
    
    return {"error": f"{filename}.html not found"}


@app.get("/style.css")
async def serve_style():
    css_path = STATIC_DIR / "style.css"
    if css_path.exists():
        response = FileResponse(css_path)
        response.headers["Cache-Control"] = "public, max-age=3600"
        return response
    return {"error": "style.css not found"}


@app.get("/cache-manager.js")
async def serve_cache_manager():
    cache_path = STATIC_DIR / "cache-manager.js"
    if cache_path.exists():
        response = FileResponse(cache_path, media_type="application/javascript")
        response.headers["Cache-Control"] = "public, max-age=3600"
        return response
    return {"error": "cache-manager.js not found"}


@app.get("/{filename}.js")
async def serve_js_file(filename: str):
    """Serve any JavaScript file from root directory"""
    js_path = STATIC_DIR / f"{filename}.js"
    if js_path.exists():
        response = FileResponse(js_path, media_type="application/javascript")
        response.headers["Cache-Control"] = "public, max-age=3600"
        return response
    return {"error": f"{filename}.js not found"}


@app.get("/static/{path:path}")
async def serve_static(path: str):
    """Serve any static file from backend/static"""
    static_path = BACKEND_STATIC_DIR / path
    if static_path.exists() and static_path.is_file():
        return FileResponse(static_path)
    return {"error": f"Static file {path} not found"}


# Catch-all route - THIS MUST BE LAST!
@app.get("/{path:path}")
async def serve_catch_all(path: str):
    """Catch-all for paths without extensions"""
    if path.startswith("api/"):
        raise HTTPException(404, "API endpoint not found")
    
    html_path = STATIC_DIR / f"{path}.html"
    if html_path.exists():
        response = FileResponse(html_path)
        response.headers["Cache-Control"] = "public, max-age=3600"
        return response
    
    backend_html_path = BACKEND_STATIC_DIR / f"{path}.html"
    if backend_html_path.exists():
        response = FileResponse(backend_html_path)
        response.headers["Cache-Control"] = "public, max-age=3600"
        return response
    
    raise HTTPException(404, f"Page not found: {path}")
