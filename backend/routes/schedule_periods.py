"""
Shift-based scheduling API: rotations, period generation, and assignments.

Rotations are stored in instance_config under the "rotations" key — one entry
per group/schedule (e.g. MICU APP, Hospitalist Nights). Periods are the atomic
date+shift slots generated from a rotation's shift definitions; assignments
link providers (or students) to periods.

  GET    /api/periods/rotations                 — list configured rotations
  POST   /api/periods/rotations                 — upsert one rotation
  DELETE /api/periods/rotations/{key}           — remove a rotation (blocks if periods exist unless force=true)
  POST   /api/periods/generate                  — create periods for a rotation over a date range
  GET    /api/periods                           — periods + assignments for rotation/date range
  PATCH  /api/periods/{period_id}               — edit one period (note, holiday, staffing bounds)
  DELETE /api/periods/{period_id}               — delete one period (blocks if assigned unless force=true)
  POST   /api/periods/{period_id}/assignments   — assign a provider/student
  DELETE /api/periods/assignments/{assignment_id}

All endpoints are admin-only for now; provider-facing views come later.
"""

import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from backend.models import (
    Faculty,
    PeriodAssignment,
    SchedulePeriod,
    get_db,
)
from backend.auth import require_admin
from backend.routes.config import _get, _set

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/periods", tags=["schedule-periods"])

VALID_ROLES = {"provider", "student"}


# ── Pydantic models ───────────────────────────────────────────────────────────

class ShiftDef(BaseModel):
    key: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=80)
    start: str = Field(pattern=r"^\d{2}:\d{2}$")
    end: str = Field(pattern=r"^\d{2}:\d{2}$")
    min_slots: int = Field(default=1, ge=0, le=20)
    target_slots: int = Field(default=1, ge=0, le=20)
    max_slots: int = Field(default=1, ge=0, le=20)
    days_of_week: Optional[list[int]] = None  # 0=Mon … 6=Sun; None = every day


class RotationDef(BaseModel):
    key: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=80)
    model: str = Field(default="shift_based")  # shift_based | weekly_blocks
    division_key: Optional[str] = None         # which division owns this rotation
    color: Optional[str] = None
    roles: list[str] = Field(default_factory=lambda: ["provider"])
    shifts: list[ShiftDef] = Field(default_factory=list)


class GenerateRequest(BaseModel):
    rotation_key: str
    start_date: date
    end_date: date


class PeriodPatch(BaseModel):
    note: Optional[str] = None
    is_holiday: Optional[bool] = None
    slots_needed: Optional[int] = Field(default=None, ge=0, le=20)
    min_slots: Optional[int] = Field(default=None, ge=0, le=20)
    max_slots: Optional[int] = Field(default=None, ge=0, le=20)


class AssignmentCreate(BaseModel):
    provider_id: str
    role: str = "provider"
    status: str = "assigned"
    note: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rotations(db: Session) -> list[dict]:
    return _get(db, "rotations") or []


def _find_rotation(db: Session, key: str) -> dict:
    for r in _rotations(db):
        if r.get("key") == key:
            return r
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Unknown rotation: '{key}'")


def _serialize_assignment(a: PeriodAssignment) -> dict:
    return {
        "id": a.id,
        "provider_id": a.provider_id,
        "provider_name": a.provider.name if a.provider else a.provider_id,
        "role": a.role,
        "status": a.status,
        "is_manual": a.is_manual,
        "note": a.note,
    }


def _serialize_period(p: SchedulePeriod) -> dict:
    provider_count = sum(1 for a in p.assignments if a.role == "provider")
    if provider_count < p.min_slots:
        fill_state = "understaffed"
    elif provider_count < p.slots_needed:
        fill_state = "below_target"
    elif provider_count <= p.slots_needed:
        fill_state = "at_target"
    else:
        fill_state = "above_target"
    return {
        "id": p.id,
        "rotation_key": p.rotation_key,
        "period_date": p.period_date.isoformat(),
        "shift_type": p.shift_type,
        "start_time": p.start_time,
        "end_time": p.end_time,
        "min_slots": p.min_slots,
        "target_slots": p.slots_needed,
        "max_slots": p.max_slots,
        "is_holiday": p.is_holiday,
        "note": p.note,
        "provider_count": provider_count,
        "fill_state": fill_state,
        "assignments": [_serialize_assignment(a) for a in p.assignments],
    }


# ── Rotation config endpoints ─────────────────────────────────────────────────

@router.get("/rotations")
def list_rotations(db: Session = Depends(get_db), admin=Depends(require_admin)):
    return _rotations(db)


@router.post("/rotations")
def upsert_rotation(
    rotation: RotationDef,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    if rotation.model == "shift_based":
        if not rotation.shifts:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="A shift_based rotation needs at least one shift.")
        seen = set()
        for s in rotation.shifts:
            if s.key in seen:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail=f"Duplicate shift key '{s.key}'.")
            seen.add(s.key)
            if not (s.min_slots <= s.target_slots <= s.max_slots):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Shift '{s.key}': need min_slots <= target_slots <= max_slots.",
                )
    for role in rotation.roles:
        if role not in VALID_ROLES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"Unknown role '{role}'. Valid: {sorted(VALID_ROLES)}")

    rotations = _rotations(db)
    entry = rotation.model_dump()
    for i, r in enumerate(rotations):
        if r.get("key") == rotation.key:
            rotations[i] = entry
            break
    else:
        rotations.append(entry)
    _set(db, "rotations", rotations)
    logger.info("Rotation '%s' saved by admin %s", rotation.key, admin.id)
    return entry


@router.delete("/rotations/{key}")
def delete_rotation(
    key: str,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    rotations = _rotations(db)
    if not any(r.get("key") == key for r in rotations):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Unknown rotation: '{key}'")
    period_count = db.query(SchedulePeriod).filter_by(rotation_key=key).count()
    if period_count and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Rotation '{key}' has {period_count} generated periods. "
                   f"Pass force=true to delete the rotation and all its periods.",
        )
    if period_count:
        db.query(SchedulePeriod).filter_by(rotation_key=key).delete()
        db.commit()
    _set(db, "rotations", [r for r in rotations if r.get("key") != key])
    logger.info("Rotation '%s' deleted (periods removed: %d) by admin %s", key, period_count, admin.id)
    return {"deleted": key, "periods_removed": period_count}


# ── Period generation ─────────────────────────────────────────────────────────

@router.post("/generate")
def generate_periods(
    req: GenerateRequest,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    """
    Create one period per date per shift for the rotation over [start_date, end_date].
    Existing periods are left untouched, so re-running for an overlapping range
    is safe and only fills gaps.
    """
    rotation = _find_rotation(db, req.rotation_key)
    if rotation.get("model") != "shift_based":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Rotation '{req.rotation_key}' is not shift_based.")
    if req.end_date < req.start_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="end_date must be on or after start_date.")
    if (req.end_date - req.start_date).days > 400:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Range too large — generate at most 400 days at a time.")

    existing = {
        (p.period_date, p.shift_type)
        for p in db.query(SchedulePeriod)
        .filter(SchedulePeriod.rotation_key == req.rotation_key,
                SchedulePeriod.period_date >= req.start_date,
                SchedulePeriod.period_date <= req.end_date)
        .all()
    }

    created = 0
    day = req.start_date
    while day <= req.end_date:
        for shift in rotation.get("shifts", []):
            dows = shift.get("days_of_week")
            if dows and day.weekday() not in dows:
                continue
            if (day, shift["key"]) in existing:
                continue
            db.add(SchedulePeriod(
                rotation_key=req.rotation_key,
                period_date=day,
                shift_type=shift["key"],
                start_time=shift.get("start", "07:00"),
                end_time=shift.get("end", "19:00"),
                slots_needed=shift.get("target_slots", 1),
                min_slots=shift.get("min_slots", 1),
                max_slots=shift.get("max_slots", shift.get("target_slots", 1)),
            ))
            created += 1
        day += timedelta(days=1)

    db.commit()
    logger.info("Generated %d periods for rotation '%s' (%s–%s) by admin %s",
                created, req.rotation_key, req.start_date, req.end_date, admin.id)
    return {"rotation_key": req.rotation_key, "created": created,
            "skipped_existing": len(existing)}


# ── Period listing / editing ──────────────────────────────────────────────────

@router.get("")
def list_periods(
    rotation_key: str = Query(...),
    start: date = Query(...),
    end: date = Query(...),
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    _find_rotation(db, rotation_key)  # 404 on unknown rotation
    periods = (
        db.query(SchedulePeriod)
        .options(joinedload(SchedulePeriod.assignments)
                 .joinedload(PeriodAssignment.provider))
        .filter(SchedulePeriod.rotation_key == rotation_key,
                SchedulePeriod.period_date >= start,
                SchedulePeriod.period_date <= end)
        .order_by(SchedulePeriod.period_date, SchedulePeriod.start_time)
        .all()
    )
    return [_serialize_period(p) for p in periods]


@router.patch("/{period_id}")
def patch_period(
    period_id: str,
    body: PeriodPatch,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    period = db.query(SchedulePeriod).filter_by(id=period_id).first()
    if not period:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Period not found.")
    for field in ("note", "is_holiday", "slots_needed", "min_slots", "max_slots"):
        value = getattr(body, field)
        if value is not None:
            setattr(period, field, value)
    if not (period.min_slots <= period.slots_needed <= period.max_slots):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Need min_slots <= target <= max_slots.")
    db.commit()
    db.refresh(period)
    return _serialize_period(period)


@router.delete("/{period_id}")
def delete_period(
    period_id: str,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    period = db.query(SchedulePeriod).filter_by(id=period_id).first()
    if not period:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Period not found.")
    if period.assignments and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Period has {len(period.assignments)} assignments. Pass force=true to delete anyway.",
        )
    db.delete(period)
    db.commit()
    return {"deleted": period_id}


# ── Assignments ───────────────────────────────────────────────────────────────

@router.post("/{period_id}/assignments")
def create_assignment(
    period_id: str,
    body: AssignmentCreate,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    period = (
        db.query(SchedulePeriod)
        .options(joinedload(SchedulePeriod.assignments))
        .filter_by(id=period_id)
        .first()
    )
    if not period:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Period not found.")
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Unknown role '{body.role}'. Valid: {sorted(VALID_ROLES)}")
    provider = db.query(Faculty).filter_by(id=body.provider_id).first()
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Unknown provider: '{body.provider_id}'")
    if any(a.provider_id == body.provider_id for a in period.assignments):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"{provider.name} is already on this shift.")

    # Providers are capped at max_slots; students never count toward staffing.
    if body.role == "provider":
        provider_count = sum(1 for a in period.assignments if a.role == "provider")
        if provider_count >= period.max_slots:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Shift already at max staffing ({period.max_slots}). "
                       f"Raise max_slots on this period to add more.",
            )

    # Warn-worthy but allowed: same provider on another shift the same date.
    same_day_other = (
        db.query(PeriodAssignment)
        .join(SchedulePeriod)
        .filter(PeriodAssignment.provider_id == body.provider_id,
                SchedulePeriod.period_date == period.period_date,
                SchedulePeriod.id != period.id)
        .count()
    )

    assignment = PeriodAssignment(
        period_id=period.id,
        provider_id=body.provider_id,
        role=body.role,
        status=body.status,
        is_manual=True,
        assigned_by=admin.id,
        note=body.note,
    )
    db.add(assignment)
    db.commit()
    db.refresh(period)
    result = _serialize_period(period)
    if same_day_other:
        result["warning"] = (
            f"{provider.name} is also assigned to {same_day_other} other "
            f"shift(s) on {period.period_date.isoformat()}."
        )
    return result


@router.delete("/assignments/{assignment_id}")
def delete_assignment(
    assignment_id: str,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    assignment = db.query(PeriodAssignment).filter_by(id=assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found.")
    period_id = assignment.period_id
    db.delete(assignment)
    db.commit()
    period = (
        db.query(SchedulePeriod)
        .options(joinedload(SchedulePeriod.assignments)
                 .joinedload(PeriodAssignment.provider))
        .filter_by(id=period_id)
        .first()
    )
    return _serialize_period(period) if period else {"deleted": assignment_id}
