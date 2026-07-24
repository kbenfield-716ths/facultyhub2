"""
Admin night-shift scheduling — DOM Hospitalist Nights.

Covers the full quarter lifecycle:
  draft -> open_for_preferences -> building -> published -> archived

  POST   /api/admin/night-schedule/quarters
  GET    /api/admin/night-schedule/quarters
  GET    /api/admin/night-schedule/quarters/{id}
  PATCH  /api/admin/night-schedule/quarters/{id}
  POST   /api/admin/night-schedule/quarters/{id}/generate-periods

  GET    /api/admin/night-schedule/quarters/{id}/blocked-nights
  POST   /api/admin/night-schedule/quarters/{id}/blocked-nights
  POST   /api/admin/night-schedule/quarters/{id}/blocked-nights/import   (CSV)
  DELETE /api/admin/night-schedule/quarters/{id}/blocked-nights/{bid}

  GET    /api/admin/night-schedule/quarters/{id}/quotas
  PUT    /api/admin/night-schedule/quarters/{id}/quotas/{provider_id}
  DELETE /api/admin/night-schedule/quarters/{id}/quotas/{provider_id}

  GET    /api/admin/night-schedule/quarters/{id}/preferences-status

  POST   /api/admin/night-schedule/quarters/{id}/preview
  POST   /api/admin/night-schedule/quarters/{id}/build

  GET    /api/admin/night-schedule/quarters/{id}/schedule
  PUT    /api/admin/night-schedule/quarters/{id}/schedule/{period_id}
  GET    /api/admin/night-schedule/quarters/{id}/export   (CSV)
"""

import csv
import io
import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models import (
    Faculty, Quarter, SchedulePeriod, PeriodAssignment,
    BlockedNight, NightPreference, ProviderNightQuota, get_db,
)
from backend.auth import require_admin
from backend.security import log_audit
from backend.night_schedule_generator import compute_assignments, apply_assignments, _provider_lanes


def _night_scheduling_pool(db: Session) -> List[Faculty]:
    """Active providers eligible for night-shift scheduling.

    Mirrors the candidate-pool filter in night_schedule_generator: excludes
    admin-only accounts (e.g. the system ADMIN user) unless they've been
    explicitly opted in via extra_config["lanes"].
    """
    return [
        p for p in db.query(Faculty).filter_by(active=True).order_by(Faculty.name).all()
        if not p.is_admin or _provider_lanes(p) is not None
    ]

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/night-schedule", tags=["night-schedule"])

# The two night lanes for this instance. Both run 19:00-07:00, one slot each.
LANES = [
    {"key": "admitter", "label": "Admitter", "start": "19:00", "end": "07:00", "slots_needed": 1},
    {"key": "nocturnist", "label": "Nocturnist", "start": "19:00", "end": "07:00", "slots_needed": 1},
]
LANE_KEYS = [lane["key"] for lane in LANES]


# ── Pydantic ──────────────────────────────────────────────────────────────────

class QuarterCreate(BaseModel):
    name: str
    start_date: date
    end_date: date
    default_quota: int = 0
    preference_deadline: Optional[datetime] = None
    notes: Optional[str] = None


class QuarterUpdate(BaseModel):
    name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None
    default_quota: Optional[int] = None
    preference_deadline: Optional[datetime] = None
    notes: Optional[str] = None


VALID_STATUSES = {"draft", "open_for_preferences", "building", "published", "archived"}


class BlockedNightCreate(BaseModel):
    provider_id: str
    night_date: date
    note: Optional[str] = None


class QuotaSet(BaseModel):
    target_nights: int
    note: Optional[str] = None


class ScheduleSlotUpdate(BaseModel):
    provider_id: Optional[str] = None  # None clears the slot
    note: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_quarter_or_404(db: Session, quarter_id: str) -> Quarter:
    q = db.query(Quarter).filter_by(id=quarter_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Quarter not found")
    return q


def _quarter_summary(db: Session, q: Quarter) -> dict:
    period_count = db.query(func.count(SchedulePeriod.id)).filter_by(rotation_key=q.id).scalar() or 0
    blocked_count = db.query(func.count(BlockedNight.id)).filter_by(quarter_id=q.id).scalar() or 0
    pref_count = db.query(func.count(NightPreference.id)).filter_by(quarter_id=q.id).scalar() or 0
    return {
        "id": q.id,
        "name": q.name,
        "start_date": q.start_date.isoformat(),
        "end_date": q.end_date.isoformat(),
        "status": q.status,
        "default_quota": q.default_quota,
        "preference_deadline": q.preference_deadline.isoformat() if q.preference_deadline else None,
        "notes": q.notes,
        "period_count": period_count,
        "blocked_count": blocked_count,
        "preference_count": pref_count,
        "created_at": q.created_at.isoformat() if q.created_at else None,
    }


def _daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


# ── Quarter CRUD ─────────────────────────────────────────────────────────────

@router.post("/quarters", status_code=201)
def create_quarter(
    body: QuarterCreate,
    request: Request,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if body.end_date < body.start_date:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")
    q = Quarter(
        name=body.name,
        start_date=body.start_date,
        end_date=body.end_date,
        default_quota=body.default_quota,
        preference_deadline=body.preference_deadline,
        notes=body.notes,
        created_by=admin.id,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    log_audit(db, admin, "create_quarter", "quarter", q.id, {"name": q.name}, request)
    return _quarter_summary(db, q)


@router.get("/quarters")
def list_quarters(
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    quarters = db.query(Quarter).order_by(Quarter.start_date.desc()).all()
    return [_quarter_summary(db, q) for q in quarters]


@router.get("/quarters/{quarter_id}")
def get_quarter(
    quarter_id: str,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = _get_quarter_or_404(db, quarter_id)
    return _quarter_summary(db, q)


@router.patch("/quarters/{quarter_id}")
def update_quarter(
    quarter_id: str,
    body: QuarterUpdate,
    request: Request,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = _get_quarter_or_404(db, quarter_id)
    data = body.dict(exclude_unset=True)
    if "status" in data and data["status"] not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Valid: {sorted(VALID_STATUSES)}")
    for field, value in data.items():
        setattr(q, field, value)
    db.commit()
    db.refresh(q)
    log_audit(db, admin, "update_quarter", "quarter", q.id, data, request)
    return _quarter_summary(db, q)


@router.post("/quarters/{quarter_id}/generate-periods")
def generate_periods(
    quarter_id: str,
    request: Request,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Create one SchedulePeriod per (night, lane) for the quarter's date range.
    Idempotent — existing periods (same rotation_key/date/shift_type) are left
    untouched, only missing ones are created.
    """
    q = _get_quarter_or_404(db, quarter_id)

    existing = db.query(SchedulePeriod.period_date, SchedulePeriod.shift_type).filter_by(
        rotation_key=q.id
    ).all()
    existing_set = {(d, s) for d, s in existing}

    created = 0
    for d in _daterange(q.start_date, q.end_date):
        for lane in LANES:
            if (d, lane["key"]) in existing_set:
                continue
            db.add(SchedulePeriod(
                rotation_key=q.id,
                period_date=d,
                shift_type=lane["key"],
                start_time=lane["start"],
                end_time=lane["end"],
                slots_needed=lane["slots_needed"],
            ))
            created += 1

    db.commit()
    log_audit(db, admin, "generate_periods", "quarter", q.id, {"created": created}, request)
    return {"created": created, "total_nights": (q.end_date - q.start_date).days + 1, "lanes": LANE_KEYS}


# ── Blocked nights ───────────────────────────────────────────────────────────

@router.get("/quarters/{quarter_id}/blocked-nights")
def list_blocked_nights(
    quarter_id: str,
    provider_id: Optional[str] = None,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _get_quarter_or_404(db, quarter_id)
    query = db.query(BlockedNight).filter_by(quarter_id=quarter_id)
    if provider_id:
        query = query.filter_by(provider_id=provider_id)
    rows = query.order_by(BlockedNight.provider_id, BlockedNight.night_date).all()

    names = {f.id: f.name for f in db.query(Faculty).all()}
    return [
        {
            "id": r.id,
            "provider_id": r.provider_id,
            "provider_name": names.get(r.provider_id, r.provider_id),
            "night_date": r.night_date.isoformat(),
            "source": r.source,
            "note": r.note,
        }
        for r in rows
    ]


@router.post("/quarters/{quarter_id}/blocked-nights", status_code=201)
def add_blocked_night(
    quarter_id: str,
    body: BlockedNightCreate,
    request: Request,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = _get_quarter_or_404(db, quarter_id)
    if not db.query(Faculty).filter_by(id=body.provider_id).first():
        raise HTTPException(status_code=404, detail=f"Provider '{body.provider_id}' not found")
    if body.night_date < q.start_date or body.night_date > q.end_date:
        raise HTTPException(status_code=400, detail="night_date is outside the quarter's date range")

    existing = db.query(BlockedNight).filter_by(
        quarter_id=quarter_id, provider_id=body.provider_id, night_date=body.night_date
    ).first()
    if existing:
        return {"id": existing.id, "already_existed": True}

    row = BlockedNight(
        quarter_id=quarter_id,
        provider_id=body.provider_id,
        night_date=body.night_date,
        source="manual",
        note=body.note,
        created_by=admin.id,
    )
    db.add(row)

    # A blocked night cannot also carry a preference.
    db.query(NightPreference).filter_by(
        quarter_id=quarter_id, provider_id=body.provider_id, night_date=body.night_date
    ).delete()

    db.commit()
    log_audit(db, admin, "add_blocked_night", "quarter", quarter_id,
              {"provider_id": body.provider_id, "date": body.night_date.isoformat()}, request)
    return {"id": row.id, "already_existed": False}


@router.post("/quarters/{quarter_id}/blocked-nights/import")
async def import_blocked_nights(
    quarter_id: str,
    request: Request,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Bulk-import blocked nights from a CSV body.

    Expected columns (header row required, case-insensitive):
      provider_id (or email), date  (YYYY-MM-DD)

    Any other columns are ignored. Rows referencing an unknown provider or a
    date outside the quarter's range are skipped and reported back.
    """
    q = _get_quarter_or_404(db, quarter_id)

    raw = await request.body()
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="CSV appears to be empty or missing a header row")

    fieldmap = {f.lower().strip(): f for f in reader.fieldnames}
    id_col = fieldmap.get("provider_id") or fieldmap.get("email") or fieldmap.get("id")
    date_col = fieldmap.get("date") or fieldmap.get("night_date")
    if not id_col or not date_col:
        raise HTTPException(
            status_code=400,
            detail="CSV must have a 'provider_id' (or 'email') column and a 'date' column",
        )

    faculty_by_id = {f.id: f for f in db.query(Faculty).all()}
    faculty_by_email = {f.email.lower(): f for f in faculty_by_id.values() if f.email}

    imported = 0
    skipped = []
    for i, row in enumerate(reader, start=2):  # row 1 is the header
        raw_id = (row.get(id_col) or "").strip()
        raw_date = (row.get(date_col) or "").strip()
        if not raw_id or not raw_date:
            continue

        faculty = faculty_by_id.get(raw_id) or faculty_by_email.get(raw_id.lower())
        if not faculty:
            skipped.append({"row": i, "reason": f"unknown provider '{raw_id}'"})
            continue

        try:
            night_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            skipped.append({"row": i, "reason": f"unparseable date '{raw_date}' (expected YYYY-MM-DD)"})
            continue

        if night_date < q.start_date or night_date > q.end_date:
            skipped.append({"row": i, "reason": f"date {raw_date} is outside the quarter"})
            continue

        existing = db.query(BlockedNight).filter_by(
            quarter_id=quarter_id, provider_id=faculty.id, night_date=night_date
        ).first()
        if existing:
            continue

        db.add(BlockedNight(
            quarter_id=quarter_id,
            provider_id=faculty.id,
            night_date=night_date,
            source="import",
            created_by=admin.id,
        ))
        db.query(NightPreference).filter_by(
            quarter_id=quarter_id, provider_id=faculty.id, night_date=night_date
        ).delete()
        imported += 1

    db.commit()
    log_audit(db, admin, "import_blocked_nights", "quarter", quarter_id,
              {"imported": imported, "skipped": len(skipped)}, request)
    return {"imported": imported, "skipped": skipped}


@router.delete("/quarters/{quarter_id}/blocked-nights/{blocked_id}", status_code=204)
def delete_blocked_night(
    quarter_id: str,
    blocked_id: str,
    request: Request,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(BlockedNight).filter_by(id=blocked_id, quarter_id=quarter_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Blocked night not found")
    db.delete(row)
    db.commit()
    log_audit(db, admin, "delete_blocked_night", "quarter", quarter_id, {"blocked_id": blocked_id}, request)
    return None


# ── Quotas ───────────────────────────────────────────────────────────────────

@router.get("/quarters/{quarter_id}/quotas")
def list_quotas(
    quarter_id: str,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = _get_quarter_or_404(db, quarter_id)
    overrides = {r.provider_id: r for r in db.query(ProviderNightQuota).filter_by(quarter_id=quarter_id).all()}
    providers = _night_scheduling_pool(db)

    return {
        "default_quota": q.default_quota,
        "providers": [
            {
                "provider_id": p.id,
                "name": p.name,
                "target_nights": overrides[p.id].target_nights if p.id in overrides else q.default_quota,
                "is_override": p.id in overrides,
                "note": overrides[p.id].note if p.id in overrides else None,
            }
            for p in providers
        ],
    }


@router.put("/quarters/{quarter_id}/quotas/{provider_id}")
def set_quota(
    quarter_id: str,
    provider_id: str,
    body: QuotaSet,
    request: Request,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _get_quarter_or_404(db, quarter_id)
    if not db.query(Faculty).filter_by(id=provider_id).first():
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")
    if body.target_nights < 0:
        raise HTTPException(status_code=400, detail="target_nights cannot be negative")

    row = db.query(ProviderNightQuota).filter_by(quarter_id=quarter_id, provider_id=provider_id).first()
    if row:
        row.target_nights = body.target_nights
        row.note = body.note
    else:
        row = ProviderNightQuota(
            quarter_id=quarter_id, provider_id=provider_id,
            target_nights=body.target_nights, note=body.note,
        )
        db.add(row)
    db.commit()
    log_audit(db, admin, "set_night_quota", "quarter", quarter_id,
              {"provider_id": provider_id, "target_nights": body.target_nights}, request)
    return {"provider_id": provider_id, "target_nights": body.target_nights, "note": body.note}


@router.delete("/quarters/{quarter_id}/quotas/{provider_id}", status_code=204)
def clear_quota_override(
    quarter_id: str,
    provider_id: str,
    request: Request,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(ProviderNightQuota).filter_by(quarter_id=quarter_id, provider_id=provider_id).first()
    if row:
        db.delete(row)
        db.commit()
        log_audit(db, admin, "clear_night_quota", "quarter", quarter_id, {"provider_id": provider_id}, request)
    return None


# ── Preference submission status ────────────────────────────────────────────

@router.get("/quarters/{quarter_id}/preferences-status")
def preferences_status(
    quarter_id: str,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = _get_quarter_or_404(db, quarter_id)
    overrides = {r.provider_id: r.target_nights for r in db.query(ProviderNightQuota).filter_by(quarter_id=quarter_id).all()}
    providers = _night_scheduling_pool(db)

    prefs = db.query(NightPreference).filter_by(quarter_id=quarter_id).all()
    by_provider: Dict[str, Dict[str, int]] = {}
    for p in prefs:
        bucket = by_provider.setdefault(p.provider_id, {"preferred": 0, "can_work": 0})
        bucket[p.preference] = bucket.get(p.preference, 0) + 1

    blocked_counts: Dict[str, int] = {}
    for r in db.query(BlockedNight.provider_id, func.count(BlockedNight.id)).filter_by(quarter_id=quarter_id).group_by(BlockedNight.provider_id).all():
        blocked_counts[r[0]] = r[1]

    return {
        "preference_deadline": q.preference_deadline.isoformat() if q.preference_deadline else None,
        "providers": [
            {
                "provider_id": p.id,
                "name": p.name,
                "target_nights": overrides.get(p.id, q.default_quota),
                "preferred_count": by_provider.get(p.id, {}).get("preferred", 0),
                "can_work_count": by_provider.get(p.id, {}).get("can_work", 0),
                "blocked_count": blocked_counts.get(p.id, 0),
                "submitted": p.id in by_provider,
            }
            for p in providers
        ],
    }


# ── Builder ──────────────────────────────────────────────────────────────────

@router.post("/quarters/{quarter_id}/preview")
def preview_build(
    quarter_id: str,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = _get_quarter_or_404(db, quarter_id)
    if db.query(func.count(SchedulePeriod.id)).filter_by(rotation_key=q.id).scalar() == 0:
        raise HTTPException(status_code=400, detail="No periods generated for this quarter yet. Run generate-periods first.")
    return compute_assignments(db, q)


@router.post("/quarters/{quarter_id}/build")
def run_build(
    quarter_id: str,
    request: Request,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = _get_quarter_or_404(db, quarter_id)
    if db.query(func.count(SchedulePeriod.id)).filter_by(rotation_key=q.id).scalar() == 0:
        raise HTTPException(status_code=400, detail="No periods generated for this quarter yet. Run generate-periods first.")
    plan = compute_assignments(db, q)
    result = apply_assignments(db, q, plan, admin_id=admin.id)
    log_audit(db, admin, "build_night_schedule", "quarter", quarter_id,
              {"applied": result["applied"], "unfilled": len(plan["unfilled"])}, request)
    return {**result, "unfilled": plan["unfilled"], "quota_summary": plan["quota_summary"]}


# ── Schedule grid (admin view + manual overrides) ───────────────────────────

@router.get("/quarters/{quarter_id}/schedule")
def get_schedule(
    quarter_id: str,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = _get_quarter_or_404(db, quarter_id)
    periods = db.query(SchedulePeriod).filter_by(rotation_key=q.id).order_by(
        SchedulePeriod.period_date, SchedulePeriod.shift_type
    ).all()
    period_ids = [p.id for p in periods]
    assignments = []
    if period_ids:
        assignments = db.query(PeriodAssignment).filter(PeriodAssignment.period_id.in_(period_ids)).all()
    by_period = {a.period_id: a for a in assignments}
    names = {f.id: f.name for f in db.query(Faculty).all()}

    days: Dict[str, dict] = {}
    for p in periods:
        day = days.setdefault(p.period_date.isoformat(), {"date": p.period_date.isoformat(), "lanes": {}})
        a = by_period.get(p.id)
        day["lanes"][p.shift_type] = {
            "period_id": p.id,
            "provider_id": a.provider_id if a else None,
            "provider_name": names.get(a.provider_id) if a else None,
            "is_manual": a.is_manual if a else None,
            "note": a.note if a else None,
        }

    return {"quarter_id": q.id, "status": q.status, "days": list(days.values())}


@router.put("/quarters/{quarter_id}/schedule/{period_id}")
def set_schedule_slot(
    quarter_id: str,
    period_id: str,
    body: ScheduleSlotUpdate,
    request: Request,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Manually assign, reassign, or clear one (date, lane) slot."""
    _get_quarter_or_404(db, quarter_id)
    period = db.query(SchedulePeriod).filter_by(id=period_id, rotation_key=quarter_id).first()
    if not period:
        raise HTTPException(status_code=404, detail="Period not found in this quarter")

    existing = db.query(PeriodAssignment).filter_by(period_id=period_id).first()

    if body.provider_id is None:
        if existing:
            db.delete(existing)
            db.commit()
        log_audit(db, admin, "clear_schedule_slot", "period", period_id,
                  {"date": period.period_date.isoformat(), "lane": period.shift_type}, request)
        return {"period_id": period_id, "provider_id": None}

    if not db.query(Faculty).filter_by(id=body.provider_id).first():
        raise HTTPException(status_code=404, detail=f"Provider '{body.provider_id}' not found")

    # Prevent double-booking the same provider on the same night in the other lane.
    sibling = db.query(SchedulePeriod).filter(
        SchedulePeriod.rotation_key == quarter_id,
        SchedulePeriod.period_date == period.period_date,
        SchedulePeriod.id != period_id,
    ).first()
    if sibling:
        sibling_assignment = db.query(PeriodAssignment).filter_by(
            period_id=sibling.id, provider_id=body.provider_id
        ).first()
        if sibling_assignment:
            raise HTTPException(
                status_code=400,
                detail=f"Provider is already assigned to {sibling.shift_type} on {period.period_date.isoformat()}",
            )

    if existing:
        existing.provider_id = body.provider_id
        existing.is_manual = True
        existing.assigned_by = admin.id
        existing.note = body.note
        existing.status = "assigned"
    else:
        db.add(PeriodAssignment(
            period_id=period_id,
            provider_id=body.provider_id,
            status="assigned",
            is_manual=True,
            assigned_by=admin.id,
            note=body.note,
        ))
    db.commit()
    log_audit(db, admin, "set_schedule_slot", "period", period_id,
              {"date": period.period_date.isoformat(), "lane": period.shift_type, "provider_id": body.provider_id}, request)
    return {"period_id": period_id, "provider_id": body.provider_id}


# ── CSV export ───────────────────────────────────────────────────────────────

@router.get("/quarters/{quarter_id}/export")
def export_schedule(
    quarter_id: str,
    admin: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = _get_quarter_or_404(db, quarter_id)
    periods = db.query(SchedulePeriod).filter_by(rotation_key=q.id).order_by(
        SchedulePeriod.period_date, SchedulePeriod.shift_type
    ).all()
    period_ids = [p.id for p in periods]
    assignments = {}
    if period_ids:
        for a in db.query(PeriodAssignment).filter(PeriodAssignment.period_id.in_(period_ids)).all():
            assignments[a.period_id] = a
    names = {f.id: f.name for f in db.query(Faculty).all()}

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "lane", "provider_id", "provider_name", "manual"])
    for p in periods:
        a = assignments.get(p.id)
        writer.writerow([
            p.period_date.isoformat(),
            p.shift_type,
            a.provider_id if a else "",
            names.get(a.provider_id, "") if a else "",
            "yes" if (a and a.is_manual) else ("no" if a else ""),
        ])
    buf.seek(0)
    filename = f"{q.name.replace(' ', '_')}_night_schedule.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
