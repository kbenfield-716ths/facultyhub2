"""
Wave-based draft system routes
Staggered-start, first-come-first-served availability selection
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
import uuid

from ..models import (
    get_db, Faculty, ServiceWeek,
    DraftWaveConfig, DraftWave, WaveFacultyAssignment,
    WeekDraftStatus, DraftWeekRequest, FacultyBlock
)
from ..auth import get_current_user, require_admin
from ..email_service import send_email, send_wave_draft_confirmation

router = APIRouter(prefix="/api/draft-waves", tags=["draft-waves"])

# ===== Schemas =====

class WaveConfigCreate(BaseModel):
    year: int
    close_date: datetime


class WaveCreate(BaseModel):
    name: str
    open_date: datetime
    faculty_ids: List[str]


class WaveConfigOut(BaseModel):
    id: str
    year: int
    close_date: datetime
    status: str
    created_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WaveOut(BaseModel):
    id: str
    name: str
    open_date: datetime
    wave_order: int
    faculty_count: int

    class Config:
        from_attributes = True


class WeekStatusOut(BaseModel):
    week_id: str
    week_number: int
    start_date: str
    end_date: str
    unavailable_count: int
    volunteer_count: int
    unavailable_locked: bool
    volunteer_locked: bool


class SubmitRequestsPayload(BaseModel):
    unavailable_week_ids: List[str] = []
    volunteer_week_ids: List[str] = []


# ===== Helper Functions =====

def send_wave_notification(faculty: Faculty, close_date: datetime):
    """Send initial email notification when wave opens"""
    subject = "FacultyHub: Availability Request Portal is Now Open"

    close_date_str = close_date.strftime("%B %d, %Y at %I:%M %p")

    message = f"""
<html>
<body>
<h2>Dear {faculty.name},</h2>

<p>You may now begin entering your availability requests for the coming academic year.</p>

<p>The portal for making those requests will lock on <strong>{close_date_str}</strong>, after which no more requests can be submitted.</p>

<p><a href="https://facultyhub.fly.dev/service-availability.html" style="display: inline-block; padding: 12px 24px; background: #3b82f6; color: white; text-decoration: none; border-radius: 6px; font-weight: 600;">Submit Your Requests</a></p>

<p>Important reminders:</p>
<ul>
<li>Each week has limited capacity - requests are first-come, first-served</li>
<li>You cannot both request unavailability AND volunteer for the same week</li>
<li>Once a week reaches capacity, it will be locked and greyed out</li>
</ul>

<p>Best regards,<br>
FacultyHub System</p>
</body>
</html>
"""

    try:
        send_email(
            to_email=faculty.email,
            to_name=faculty.name,
            subject=subject,
            html_content=message
        )
        return True
    except Exception as e:
        print(f"Failed to send wave notification to {faculty.email}: {e}")
        return False


def send_wave_reminder(faculty: Faculty, close_date: datetime):
    """Send reminder email 48 hours after wave opens if no data entered"""
    subject = "⏰ Reminder: Availability Request Portal Still Open"

    close_date_str = close_date.strftime("%B %d, %Y at %I:%M %p")

    message = f"""
<html>
<body>
<h2>Dear {faculty.name},</h2>

<p><strong>This is a friendly reminder</strong> that your availability request portal is still open, but we haven't received any submissions from you yet.</p>

<p>The portal will lock on <strong>{close_date_str}</strong>. After that date, no more requests can be submitted.</p>

<p><a href="https://facultyhub.fly.dev/service-availability.html" style="display: inline-block; padding: 12px 24px; background: #ef4444; color: white; text-decoration: none; border-radius: 6px; font-weight: 600;">Submit Your Requests Now</a></p>

<p><strong>Why submit now?</strong></p>
<ul>
<li>Week capacity is limited - popular weeks fill up quickly</li>
<li>First-come, first-served basis for all requests</li>
<li>Ensure you can request the weeks you need</li>
</ul>

<p>If you've already submitted or don't need to make any requests, you can disregard this message.</p>

<p>Best regards,<br>
FacultyHub System</p>
</body>
</html>
"""

    try:
        send_email(
            to_email=faculty.email,
            to_name=faculty.name,
            subject=subject,
            html_content=message
        )
        return True
    except Exception as e:
        print(f"Failed to send wave reminder to {faculty.email}: {e}")
        return False


# ===== Admin Routes =====

@router.post("/admin/configs", response_model=WaveConfigOut)
def create_wave_config(
    payload: WaveConfigCreate,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Create a new wave draft configuration (admin only)"""

    # Check if config already exists for this year
    existing = db.query(DraftWaveConfig).filter_by(year=payload.year).first()
    if existing:
        raise HTTPException(400, f"Wave draft config already exists for year {payload.year}")

    config = DraftWaveConfig(
        id=str(uuid.uuid4()),
        year=payload.year,
        close_date=payload.close_date,
        status='pending'
    )

    db.add(config)
    db.commit()
    db.refresh(config)

    return config


@router.get("/admin/configs/debug")
def debug_wave_configs(
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Debug endpoint - see raw database data without Pydantic"""
    from sqlalchemy import inspect, text

    configs = db.query(DraftWaveConfig).order_by(DraftWaveConfig.year.desc()).all()

    result = []
    for config in configs:
        # Get raw attributes
        mapper = inspect(config)
        raw_data = {"_id": config.id}
        for col in mapper.mapper.column_attrs:
            value = getattr(config, col.key)
            raw_data[col.key] = {
                "value": str(value) if value else None,
                "type": str(type(value).__name__),
                "is_none": value is None
            }
        result.append(raw_data)

    # Also get raw SQL data
    raw_sql = db.execute(text("SELECT * FROM draft_wave_configs ORDER BY year DESC")).fetchall()
    sql_data = [dict(row._mapping) for row in raw_sql]

    return {
        "configs_via_orm": result,
        "configs_via_sql": sql_data,
        "count": len(result)
    }


@router.get("/admin/configs", response_model=List[WaveConfigOut])
def list_wave_configs(
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List all wave draft configurations (admin only)"""
    try:
        configs = db.query(DraftWaveConfig).order_by(DraftWaveConfig.year.desc()).all()

        # Manual serialization to debug
        result = []
        for config in configs:
            try:
                config_dict = {
                    "id": config.id,
                    "year": config.year,
                    "close_date": config.close_date,
                    "status": config.status,
                    "created_at": config.created_at,
                    "activated_at": config.activated_at,
                    "closed_at": config.closed_at
                }
                result.append(WaveConfigOut(**config_dict))
            except Exception as e:
                print(f"Error serializing config {config.id}: {e}")
                print(f"Config attributes: id={config.id}, year={config.year}, status={config.status}")
                print(f"  close_date={config.close_date} (type: {type(config.close_date)})")
                print(f"  created_at={config.created_at} (type: {type(config.created_at)})")
                print(f"  activated_at={config.activated_at} (type: {type(config.activated_at)})")
                print(f"  closed_at={config.closed_at} (type: {type(config.closed_at)})")
                import traceback
                traceback.print_exc()
                raise

        return result
    except Exception as e:
        print(f"Error listing wave configs: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load wave configurations: {str(e)}"
        )


@router.get("/admin/configs/{config_id}", response_model=WaveConfigOut)
def get_wave_config(
    config_id: str,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get specific wave draft configuration (admin only)"""
    config = db.query(DraftWaveConfig).filter_by(id=config_id).first()
    if not config:
        raise HTTPException(404, "Config not found")
    return config


@router.post("/admin/configs/{config_id}/waves", response_model=WaveOut)
def create_wave(
    config_id: str,
    payload: WaveCreate,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Create a new wave in the draft (admin only)"""

    config = db.query(DraftWaveConfig).filter_by(id=config_id).first()
    if not config:
        raise HTTPException(404, "Config not found")

    if config.status != 'pending':
        raise HTTPException(400, "Cannot add waves to active or closed config")

    # Get next wave order
    max_order = db.query(func.max(DraftWave.wave_order)).filter_by(config_id=config_id).scalar() or 0

    # Create wave
    wave = DraftWave(
        id=str(uuid.uuid4()),
        config_id=config_id,
        name=payload.name,
        open_date=payload.open_date,
        wave_order=max_order + 1
    )

    db.add(wave)
    db.flush()

    # Assign faculty to wave
    for faculty_id in payload.faculty_ids:
        # Verify faculty exists
        faculty = db.query(Faculty).filter_by(id=faculty_id).first()
        if not faculty:
            raise HTTPException(400, f"Faculty {faculty_id} not found")

        # Check if already assigned to another wave in this config
        existing_assignment = db.query(WaveFacultyAssignment).join(DraftWave).filter(
            DraftWave.config_id == config_id,
            WaveFacultyAssignment.faculty_id == faculty_id
        ).first()

        if existing_assignment:
            raise HTTPException(400, f"Faculty {faculty_id} already assigned to a wave")

        assignment = WaveFacultyAssignment(
            id=str(uuid.uuid4()),
            wave_id=wave.id,
            faculty_id=faculty_id
        )
        db.add(assignment)

    db.commit()
    db.refresh(wave)

    faculty_count = len(payload.faculty_ids)

    return WaveOut(
        id=wave.id,
        name=wave.name,
        open_date=wave.open_date,
        wave_order=wave.wave_order,
        faculty_count=faculty_count
    )


@router.get("/admin/configs/{config_id}/waves", response_model=List[WaveOut])
def list_waves(
    config_id: str,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List all waves in a config (admin only)"""

    waves = db.query(DraftWave).filter_by(config_id=config_id).order_by(DraftWave.wave_order).all()

    result = []
    for wave in waves:
        faculty_count = db.query(WaveFacultyAssignment).filter_by(wave_id=wave.id).count()
        result.append(WaveOut(
            id=wave.id,
            name=wave.name,
            open_date=wave.open_date,
            wave_order=wave.wave_order,
            faculty_count=faculty_count
        ))

    return result


@router.post("/admin/configs/{config_id}/activate")
def activate_wave_config(
    config_id: str,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Activate the wave draft system (admin only)"""

    config = db.query(DraftWaveConfig).filter_by(id=config_id).first()
    if not config:
        raise HTTPException(404, "Config not found")

    if config.status != 'pending':
        raise HTTPException(400, "Config is already active or closed")

    # Verify waves exist
    waves_count = db.query(DraftWave).filter_by(config_id=config_id).count()
    if waves_count == 0:
        raise HTTPException(400, "Cannot activate config with no waves")

    # Initialize week status for all service weeks in this year
    weeks = db.query(ServiceWeek).filter_by(year=config.year).all()
    if not weeks:
        raise HTTPException(400, f"No service weeks found for year {config.year}")

    for week in weeks:
        # Seed counts from any requests already submitted (e.g. after a reset-to-pending)
        unavailable_count = db.query(DraftWeekRequest).filter(
            DraftWeekRequest.config_id == config_id,
            DraftWeekRequest.week_id == week.id,
            DraftWeekRequest.request_type == 'unavailable'
        ).count()

        volunteer_count = db.query(DraftWeekRequest).filter(
            DraftWeekRequest.config_id == config_id,
            DraftWeekRequest.week_id == week.id,
            DraftWeekRequest.request_type == 'volunteer'
        ).count()

        week_status = WeekDraftStatus(
            id=str(uuid.uuid4()),
            config_id=config_id,
            week_id=week.id,
            unavailable_count=unavailable_count,
            volunteer_count=volunteer_count
        )
        db.add(week_status)

    # Activate config
    config.status = 'active'
    config.activated_at = datetime.utcnow()

    db.commit()

    # Send notifications to waves that should already be open
    now = datetime.utcnow()
    open_waves = db.query(DraftWave).filter(
        DraftWave.config_id == config_id,
        DraftWave.open_date <= now
    ).all()

    notifications_sent = 0
    for wave in open_waves:
        assignments = db.query(WaveFacultyAssignment).filter_by(wave_id=wave.id).all()
        for assignment in assignments:
            faculty = db.query(Faculty).filter_by(id=assignment.faculty_id).first()
            if faculty and faculty.email:
                if send_wave_notification(faculty, config.close_date):
                    assignment.notified_at = datetime.utcnow()
                    notifications_sent += 1

    if notifications_sent > 0:
        db.commit()

    return {
        "status": "activated",
        "year": config.year,
        "notifications_sent": notifications_sent
    }


@router.post("/admin/configs/{config_id}/reset-to-pending")
def reset_config_to_pending(
    config_id: str,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Reset an active config back to pending so waves can be added.
    - Clears activated_at and resets status to 'pending'
    - Deletes week_draft_status records (recreated fresh on next activate)
    - Resets notified_at / reminder_sent_at on all assignments so emails re-fire on re-activate
    - Preserves all waves and faculty assignments
    """
    config = db.query(DraftWaveConfig).filter_by(id=config_id).first()
    if not config:
        raise HTTPException(404, "Config not found")

    if config.status == 'closed':
        raise HTTPException(400, "Cannot reset a closed config")

    if config.status == 'pending':
        raise HTTPException(400, "Config is already in pending state")

    # Reset config status
    config.status = 'pending'
    config.activated_at = None

    # Remove week status rows (recreated on next activate)
    db.query(WeekDraftStatus).filter_by(config_id=config_id).delete()

    # Reset notification timestamps only for faculty who haven't submitted anything yet
    # Faculty who already submitted keep their notified_at so they don't get a duplicate email
    waves = db.query(DraftWave).filter_by(config_id=config_id).all()
    for wave in waves:
        assignments = db.query(WaveFacultyAssignment).filter_by(wave_id=wave.id).all()
        for assignment in assignments:
            has_submitted = db.query(DraftWeekRequest).filter(
                DraftWeekRequest.config_id == config_id,
                DraftWeekRequest.faculty_id == assignment.faculty_id
            ).first()
            if not has_submitted:
                assignment.notified_at = None
                assignment.reminder_sent_at = None

    db.commit()

    return {
        "status": "reset",
        "message": "Config reset to pending. Add waves then re-activate."
    }


@router.post("/admin/configs/{config_id}/process-notifications")
def process_notifications(
    config_id: str,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Automated notification processor - call this periodically (e.g., hourly cron)

    Sends two types of emails:
    1. Initial notifications: When wave open_date arrives
    2. Reminder emails: 48 hours after initial email if no data submitted
    """

    config = db.query(DraftWaveConfig).filter_by(id=config_id).first()
    if not config:
        raise HTTPException(404, "Config not found")

    if config.status != 'active':
        raise HTTPException(400, "Config must be active to send notifications")

    now = datetime.utcnow()
    initial_sent = 0
    reminders_sent = 0

    # ===== PART 1: Send initial emails to waves that just opened =====

    # Find waves where open_date has passed
    open_waves = db.query(DraftWave).filter(
        DraftWave.config_id == config_id,
        DraftWave.open_date <= now
    ).all()

    for wave in open_waves:
        # Find faculty who haven't been notified yet
        unnotified_assignments = db.query(WaveFacultyAssignment).filter(
            WaveFacultyAssignment.wave_id == wave.id,
            WaveFacultyAssignment.notified_at == None
        ).all()

        for assignment in unnotified_assignments:
            faculty = db.query(Faculty).filter_by(id=assignment.faculty_id).first()
            if faculty and faculty.email:
                if send_wave_notification(faculty, config.close_date):
                    assignment.notified_at = now
                    initial_sent += 1

    # ===== PART 2: Send reminders to faculty who haven't submitted after 48 hours =====

    # Calculate 48 hours ago
    reminder_threshold = now - timedelta(hours=48)

    for wave in open_waves:
        # Find faculty who were notified 48+ hours ago, haven't received reminder, and haven't submitted
        notified_assignments = db.query(WaveFacultyAssignment).filter(
            WaveFacultyAssignment.wave_id == wave.id,
            WaveFacultyAssignment.notified_at != None,
            WaveFacultyAssignment.notified_at <= reminder_threshold,
            WaveFacultyAssignment.reminder_sent_at == None
        ).all()

        for assignment in notified_assignments:
            # Check if faculty has submitted any requests
            has_submitted = db.query(DraftWeekRequest).filter(
                DraftWeekRequest.config_id == config_id,
                DraftWeekRequest.faculty_id == assignment.faculty_id
            ).first()

            # Only send reminder if they haven't submitted anything
            if not has_submitted:
                faculty = db.query(Faculty).filter_by(id=assignment.faculty_id).first()
                if faculty and faculty.email:
                    if send_wave_reminder(faculty, config.close_date):
                        assignment.reminder_sent_at = now
                        reminders_sent += 1

    if initial_sent > 0 or reminders_sent > 0:
        db.commit()

    return {
        "initial_notifications_sent": initial_sent,
        "reminder_notifications_sent": reminders_sent,
        "total_sent": initial_sent + reminders_sent
    }


# Keep old endpoint for backward compatibility
@router.post("/admin/configs/{config_id}/notify-due-waves")
def notify_due_waves(
    config_id: str,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Legacy endpoint - redirects to process-notifications"""
    return process_notifications(config_id, admin, db)


@router.delete("/admin/configs/{config_id}")
def delete_wave_config(
    config_id: str,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Delete a wave config and all its related data (admin only)"""

    config = db.query(DraftWaveConfig).filter_by(id=config_id).first()
    if not config:
        raise HTTPException(404, "Config not found")

    # Get all waves
    waves = db.query(DraftWave).filter_by(config_id=config_id).all()

    # Delete all related data
    for wave in waves:
        # Delete faculty assignments
        db.query(WaveFacultyAssignment).filter_by(wave_id=wave.id).delete()

    # Delete waves
    db.query(DraftWave).filter_by(config_id=config_id).delete()

    # Delete week statuses
    db.query(WeekDraftStatus).filter_by(config_id=config_id).delete()

    # Delete draft requests
    db.query(DraftWeekRequest).filter_by(config_id=config_id).delete()

    # Delete config itself
    db.delete(config)
    db.commit()

    return {"status": "deleted", "year": config.year}


@router.delete("/admin/waves/{wave_id}")
def delete_wave(
    wave_id: str,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Delete a wave (admin only - only if config is pending)"""

    wave = db.query(DraftWave).filter_by(id=wave_id).first()
    if not wave:
        raise HTTPException(404, "Wave not found")

    config = db.query(DraftWaveConfig).filter_by(id=wave.config_id).first()
    if config.status != 'pending':
        raise HTTPException(400, "Cannot delete waves from active or closed config")

    db.delete(wave)
    db.commit()

    return {"status": "deleted"}


# ===== Faculty Routes =====

@router.get("/my-status")
def get_my_wave_status(
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's wave draft status"""

    # Find active config
    config = db.query(DraftWaveConfig).filter_by(status='active').first()

    if not config:
        return {
            "has_active_draft": False,
            "message": "No active wave draft"
        }

    # Find user's wave assignment
    assignment = db.query(WaveFacultyAssignment).join(DraftWave).filter(
        DraftWave.config_id == config.id,
        WaveFacultyAssignment.faculty_id == current_user.id
    ).first()

    if not assignment:
        return {
            "has_active_draft": True,
            "in_draft": False,
            "message": "You are not assigned to any wave"
        }

    wave = db.query(DraftWave).filter_by(id=assignment.wave_id).first()

    now = datetime.utcnow()
    is_open = wave.open_date <= now
    is_closed = config.close_date <= now

    # Get user's current requests
    user_requests = db.query(DraftWeekRequest).filter(
        DraftWeekRequest.config_id == config.id,
        DraftWeekRequest.faculty_id == current_user.id
    ).all()

    unavailable_week_ids = [r.week_id for r in user_requests if r.request_type == 'unavailable']
    volunteer_week_ids = [r.week_id for r in user_requests if r.request_type == 'volunteer']

    return {
        "has_active_draft": True,
        "in_draft": True,
        "config_id": config.id,
        "year": config.year,
        "wave_name": wave.name,
        "wave_open_date": wave.open_date,
        "close_date": config.close_date,
        "is_open": is_open and not is_closed,
        "is_closed": is_closed,
        "unavailable_requests": unavailable_week_ids,
        "volunteer_requests": volunteer_week_ids,
        "total_requests": len(user_requests)
    }


@router.get("/week-status", response_model=List[WeekStatusOut])
def get_week_status(
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get status of all weeks (capacity, locked status)"""

    # Find active config
    config = db.query(DraftWaveConfig).filter_by(status='active').first()

    if not config:
        raise HTTPException(404, "No active wave draft")

    # Get all weeks with their status
    week_statuses = db.query(WeekDraftStatus).filter_by(config_id=config.id).all()

    # --- BUG FIX: Reconcile cached counts with actual DraftWeekRequest records ---
    # This corrects any drift from prior resubmission bugs
    needs_commit = False
    for ws in week_statuses:
        actual_unavail = db.query(func.count(DraftWeekRequest.id)).filter(
            DraftWeekRequest.config_id == config.id,
            DraftWeekRequest.week_id == ws.week_id,
            DraftWeekRequest.request_type == 'unavailable'
        ).scalar() or 0
        actual_vol = db.query(func.count(DraftWeekRequest.id)).filter(
            DraftWeekRequest.config_id == config.id,
            DraftWeekRequest.week_id == ws.week_id,
            DraftWeekRequest.request_type == 'volunteer'
        ).scalar() or 0

        if ws.unavailable_count != actual_unavail or ws.volunteer_count != actual_vol:
            ws.unavailable_count = actual_unavail
            ws.volunteer_count = actual_vol
            needs_commit = True

    if needs_commit:
        db.commit()

    result = []
    for ws in week_statuses:
        week = db.query(ServiceWeek).filter_by(id=ws.week_id).first()
        if week:
            # Include admin override blocks in the unavailable count
            # so capacity checks reflect true staffing availability
            block_count = db.query(func.count(FacultyBlock.id)).filter(
                FacultyBlock.week_id == ws.week_id
            ).scalar() or 0
            total_unavailable = ws.unavailable_count + block_count

            result.append(WeekStatusOut(
                week_id=week.id,
                week_number=week.week_number,
                start_date=week.start_date.isoformat(),
                end_date=week.end_date.isoformat(),
                unavailable_count=total_unavailable,
                volunteer_count=ws.volunteer_count,
                unavailable_locked=total_unavailable >= 12,
                volunteer_locked=ws.volunteer_count >= 6
            ))

    return sorted(result, key=lambda x: x.week_number)


@router.post("/submit")
def submit_requests(
    payload: SubmitRequestsPayload,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit or update availability requests"""

    # Find active config
    config = db.query(DraftWaveConfig).filter_by(status='active').first()
    if not config:
        raise HTTPException(404, "No active wave draft")

    # Check if user's wave is open
    assignment = db.query(WaveFacultyAssignment).join(DraftWave).filter(
        DraftWave.config_id == config.id,
        WaveFacultyAssignment.faculty_id == current_user.id
    ).first()

    if not assignment:
        raise HTTPException(403, "You are not in this draft")

    wave = db.query(DraftWave).filter_by(id=assignment.wave_id).first()

    now = datetime.utcnow()
    if wave.open_date > now:
        raise HTTPException(403, f"Your wave is not open yet. Opens at {wave.open_date}")

    if config.close_date <= now:
        raise HTTPException(403, "Draft submission period has closed")

    # Validate no overlap between unavailable and volunteer
    overlap = set(payload.unavailable_week_ids) & set(payload.volunteer_week_ids)
    if overlap:
        raise HTTPException(400, "Cannot request both unavailable and volunteer for the same week")

    # --- BUG FIX: Decrement WeekDraftStatus counts for OLD requests before deleting ---
    # Without this, every resubmission inflates the cached counts in WeekDraftStatus
    old_requests = db.query(DraftWeekRequest).filter(
        DraftWeekRequest.config_id == config.id,
        DraftWeekRequest.faculty_id == current_user.id
    ).all()

    for old_req in old_requests:
        old_week_status = db.query(WeekDraftStatus).filter(
            WeekDraftStatus.config_id == config.id,
            WeekDraftStatus.week_id == old_req.week_id
        ).first()
        if old_week_status:
            if old_req.request_type == 'unavailable':
                old_week_status.unavailable_count = max(0, old_week_status.unavailable_count - 1)
            elif old_req.request_type == 'volunteer':
                old_week_status.volunteer_count = max(0, old_week_status.volunteer_count - 1)

    # Now delete old requests (counts already decremented above)
    db.query(DraftWeekRequest).filter(
        DraftWeekRequest.config_id == config.id,
        DraftWeekRequest.faculty_id == current_user.id
    ).delete()

    # Process new requests
    added = []
    rejected = []

    for week_id in payload.unavailable_week_ids:
        # Check capacity
        week_status = db.query(WeekDraftStatus).filter(
            WeekDraftStatus.config_id == config.id,
            WeekDraftStatus.week_id == week_id
        ).first()

        if week_status and week_status.unavailable_count >= 12:
            rejected.append({"week_id": week_id, "type": "unavailable", "reason": "Week is full"})
            continue

        # Add request
        request = DraftWeekRequest(
            id=str(uuid.uuid4()),
            config_id=config.id,
            faculty_id=current_user.id,
            week_id=week_id,
            request_type='unavailable'
        )
        db.add(request)

        # Update count
        if week_status:
            week_status.unavailable_count += 1

        added.append({"week_id": week_id, "type": "unavailable"})

    for week_id in payload.volunteer_week_ids:
        # Check capacity
        week_status = db.query(WeekDraftStatus).filter(
            WeekDraftStatus.config_id == config.id,
            WeekDraftStatus.week_id == week_id
        ).first()

        if week_status and week_status.volunteer_count >= 6:
            rejected.append({"week_id": week_id, "type": "volunteer", "reason": "Week is full"})
            continue

        # Add request
        request = DraftWeekRequest(
            id=str(uuid.uuid4()),
            config_id=config.id,
            faculty_id=current_user.id,
            week_id=week_id,
            request_type='volunteer'
        )
        db.add(request)

        # Update count
        if week_status:
            week_status.volunteer_count += 1

        added.append({"week_id": week_id, "type": "volunteer"})

    # --- BUG FIX: Reconcile WeekDraftStatus with actual DraftWeekRequest counts ---
    # This ensures counts are always correct, even if they drifted from prior submissions
    affected_week_ids = set(payload.unavailable_week_ids) | set(payload.volunteer_week_ids) | set(old_req.week_id for old_req in old_requests)
    for wid in affected_week_ids:
        ws = db.query(WeekDraftStatus).filter(
            WeekDraftStatus.config_id == config.id,
            WeekDraftStatus.week_id == wid
        ).first()
        if ws:
            actual_unavail = db.query(func.count(DraftWeekRequest.id)).filter(
                DraftWeekRequest.config_id == config.id,
                DraftWeekRequest.week_id == wid,
                DraftWeekRequest.request_type == 'unavailable'
            ).scalar() or 0
            actual_vol = db.query(func.count(DraftWeekRequest.id)).filter(
                DraftWeekRequest.config_id == config.id,
                DraftWeekRequest.week_id == wid,
                DraftWeekRequest.request_type == 'volunteer'
            ).scalar() or 0
            ws.unavailable_count = actual_unavail
            ws.volunteer_count = actual_vol

    db.commit()

    # --- Send confirmation email ---
    try:
        # Gather week details for the email
        unavailable_weeks = []
        volunteer_weeks = []
        for item in added:
            week = db.query(ServiceWeek).filter(ServiceWeek.id == item["week_id"]).first()
            if week:
                week_info = {
                    "week_number": week.week_number,
                    "label": week.label,
                    "start_date": week.start_date.strftime("%Y-%m-%d") if week.start_date else "",
                    "end_date": week.end_date.strftime("%Y-%m-%d") if week.end_date else "",
                    "point_cost": week.point_cost_off if item["type"] == "unavailable" else 0,
                    "point_reward": week.point_reward_work if item["type"] == "volunteer" else 0
                }
                if item["type"] == "unavailable":
                    unavailable_weeks.append(week_info)
                elif item["type"] == "volunteer":
                    volunteer_weeks.append(week_info)

        # Build rejected list with week labels
        rejected_with_labels = []
        for item in rejected:
            week = db.query(ServiceWeek).filter(ServiceWeek.id == item["week_id"]).first()
            rejected_with_labels.append({
                "label": week.label if week else item["week_id"],
                "type": item["type"],
                "reason": item.get("reason", "")
            })

        academic_year = f"{config.year}-{config.year + 1}"

        send_wave_draft_confirmation(
            faculty_name=current_user.name,
            faculty_email=current_user.email,
            unavailable_weeks=unavailable_weeks,
            volunteer_weeks=volunteer_weeks,
            rejected=rejected_with_labels,
            academic_year=academic_year
        )
    except Exception as e:
        # Log but don't fail the submission if email fails
        print(f"[WARN] Failed to send wave draft confirmation email to {current_user.email}: {e}")

    return {
        "status": "submitted",
        "added": added,
        "rejected": rejected,
        "total_added": len(added),
        "total_rejected": len(rejected)
    }
