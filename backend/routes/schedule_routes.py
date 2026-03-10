# backend/routes/schedule_routes.py
"""
API routes for inpatient service schedule generation and viewing.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
import csv
import io

from backend.models import get_db, Faculty
from backend.auth import require_admin
from backend.schedule_generator import generate_schedule, get_schedule_view, SERVICE_REQUIREMENTS

router = APIRouter(prefix="/api/admin", tags=["schedule"])


class GenerateScheduleRequest(BaseModel):
    """Request to generate a schedule"""
    year: int = 2026
    clear_existing: bool = True


@router.post("/generate-service-schedule")
async def generate_service_schedule(
    request: GenerateScheduleRequest,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """
    Generate inpatient service schedule for the academic year.
    
    This will:
    1. Clear existing assignments (if clear_existing=True)
    2. Assign faculty to services based on their allocations
    3. Respect unavailability requests
    4. Enforce service requirements (MICU=2, APP-ICU=1, Procedures=1, Consults=1)
    5. Allow +/- 1 week flexibility per service
    
    Returns summary with any staffing or capacity issues found.
    """
    try:
        result = generate_schedule(
            db=db,
            year=request.year,
            clear_existing=request.clear_existing
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Schedule generation failed: {str(e)}")


@router.get("/service-schedule")
async def get_service_schedule(
    year: int = 2026,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """
    Get the current service schedule for viewing.
    
    Returns all weeks with their assignments for each service type.
    """
    try:
        result = get_schedule_view(db=db, year=year)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get schedule: {str(e)}")


@router.post("/service-schedule/cleanup-blocks")
async def cleanup_block_violations(
    year: int = 2026,
    dry_run: bool = False,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """
    Remove any auto-generated assignments that violate a FacultyBlock.

    FacultyBlocks are HARD STOPS — faculty set as blocked must never appear
    in auto-generated assignments for those weeks.  Manual (is_manual=True)
    and imported (imported=True) assignments are left untouched so the admin
    retains full control.

    Set dry_run=true to preview what would be removed without making changes.
    """
    from backend.models import ServiceWeek, ServiceWeekAssignment, FacultyBlock
    from sqlalchemy import and_

    # Get all week IDs for this year
    weeks = db.query(ServiceWeek).filter(ServiceWeek.year == year).all()
    week_ids = [w.id for w in weeks]
    week_label_map = {w.id: w.label for w in weeks}

    if not week_ids:
        return {"success": False, "error": f"No weeks found for year {year}"}

    # Build blocks lookup: set of (faculty_id, week_id)
    blocks = db.query(FacultyBlock).filter(
        FacultyBlock.week_id.in_(week_ids)
    ).all()
    blocked_pairs = {(b.faculty_id, b.week_id) for b in blocks}

    if not blocked_pairs:
        return {
            "success": True,
            "removed": 0,
            "violations": [],
            "message": "No faculty blocks found — nothing to clean up."
        }

    # Find auto-generated assignments that violate a block
    auto_assignments = db.query(ServiceWeekAssignment).filter(
        ServiceWeekAssignment.week_id.in_(week_ids),
        ServiceWeekAssignment.is_manual == False,
        ServiceWeekAssignment.imported == False
    ).all()

    # Also look up faculty names for reporting
    faculty_lookup = {f.id: f.name for f in db.query(Faculty).all()}

    violations = []
    ids_to_delete = []
    for a in auto_assignments:
        if (a.faculty_id, a.week_id) in blocked_pairs:
            violations.append({
                "assignment_id": a.id,
                "faculty_id": a.faculty_id,
                "faculty_name": faculty_lookup.get(a.faculty_id, a.faculty_id),
                "week_id": a.week_id,
                "week_label": week_label_map.get(a.week_id, a.week_id),
                "service_type": a.service_type,
            })
            ids_to_delete.append(a.id)

    if not dry_run and ids_to_delete:
        db.query(ServiceWeekAssignment).filter(
            ServiceWeekAssignment.id.in_(ids_to_delete)
        ).delete(synchronize_session=False)
        db.commit()

    return {
        "success": True,
        "dry_run": dry_run,
        "removed": len(ids_to_delete),
        "violations": violations,
        "message": (
            f"{'Would remove' if dry_run else 'Removed'} {len(ids_to_delete)} "
            f"assignment(s) that violated faculty blocks."
        )
    }


@router.post("/service-schedule/cleanup-unavailability")
async def cleanup_unavailability_violations(
    year: int = 2026,
    dry_run: bool = False,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """
    Remove auto-generated assignments that conflict with a faculty member's
    own unavailability request (status='unavailable') for the same week.

    This enforces the rule that unavailability requests are HARD STOPS for the
    auto-scheduler.  Manual (is_manual=True) and imported (imported=True)
    assignments are left untouched — the admin is responsible for those.

    Set dry_run=true to preview what would be removed without making changes.
    Returns a separate count of remaining violations from manual/imported
    assignments so the admin is aware.
    """
    from backend.models import ServiceWeek, ServiceWeekAssignment, UnavailabilityRequest, DraftWeekRequest
    from sqlalchemy import and_

    weeks = db.query(ServiceWeek).filter(ServiceWeek.year == year).all()
    week_ids = [w.id for w in weeks]
    week_label_map = {w.id: w.label for w in weeks}

    if not week_ids:
        return {"success": False, "error": f"No weeks found for year {year}"}

    # Build set of (faculty_id, week_id) that are marked unavailable
    unavail_pairs = set()
    for req in db.query(UnavailabilityRequest).filter(
        UnavailabilityRequest.week_id.in_(week_ids),
        UnavailabilityRequest.status == "unavailable"
    ).all():
        unavail_pairs.add((req.faculty_id, req.week_id))

    for req in db.query(DraftWeekRequest).filter(
        DraftWeekRequest.week_id.in_(week_ids),
        DraftWeekRequest.request_type == "unavailable"
    ).all():
        unavail_pairs.add((req.faculty_id, req.week_id))

    if not unavail_pairs:
        return {
            "success": True,
            "removed": 0,
            "violations": [],
            "manual_imported_violations": 0,
            "message": "No unavailability requests found — nothing to clean up."
        }

    faculty_lookup = {f.id: f.name for f in db.query(Faculty).all()}

    # Check auto-generated assignments
    auto_assignments = db.query(ServiceWeekAssignment).filter(
        ServiceWeekAssignment.week_id.in_(week_ids),
        ServiceWeekAssignment.is_manual == False,
        ServiceWeekAssignment.imported == False
    ).all()

    violations = []
    ids_to_delete = []
    for a in auto_assignments:
        if (a.faculty_id, a.week_id) in unavail_pairs:
            violations.append({
                "assignment_id": a.id,
                "faculty_id": a.faculty_id,
                "faculty_name": faculty_lookup.get(a.faculty_id, a.faculty_id),
                "week_id": a.week_id,
                "week_label": week_label_map.get(a.week_id, a.week_id),
                "service_type": a.service_type,
            })
            ids_to_delete.append(a.id)

    # Also count manual/imported violations (reported but NOT deleted)
    other_assignments = db.query(ServiceWeekAssignment).filter(
        ServiceWeekAssignment.week_id.in_(week_ids),
        ServiceWeekAssignment.is_manual == True if False else ServiceWeekAssignment.imported == True
    ).all()
    # Actually check both manual and imported
    all_other = db.query(ServiceWeekAssignment).filter(
        ServiceWeekAssignment.week_id.in_(week_ids),
        ServiceWeekAssignment.id.notin_(ids_to_delete)
    ).all()
    manual_imported_violations = sum(
        1 for a in all_other
        if (a.is_manual or a.imported) and (a.faculty_id, a.week_id) in unavail_pairs
    )

    if not dry_run and ids_to_delete:
        db.query(ServiceWeekAssignment).filter(
            ServiceWeekAssignment.id.in_(ids_to_delete)
        ).delete(synchronize_session=False)
        db.commit()

    msg = f"{'Would remove' if dry_run else 'Removed'} {len(ids_to_delete)} auto-generated assignment(s) that violated unavailability requests."
    if manual_imported_violations > 0:
        msg += f" Note: {manual_imported_violations} manual/imported assignment(s) also conflict — review those manually."

    return {
        "success": True,
        "dry_run": dry_run,
        "removed": len(ids_to_delete),
        "violations": violations,
        "manual_imported_violations": manual_imported_violations,
        "message": msg
    }


@router.get("/service-schedule/export")
async def export_service_schedule_csv(
    year: int = 2026,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """
    Export the full service schedule as a CSV file.

    Columns: Week #, Start Date, End Date, Week Type, then one column per
    service slot (MICU 1, MICU 2, APP-ICU, Procedures, Consults, Backup).
    Blocked faculty are noted with [BLOCKED].
    """
    from backend.models import ServiceWeek, ServiceWeekAssignment, FacultyBlock

    weeks = db.query(ServiceWeek).filter(
        ServiceWeek.year == year
    ).order_by(ServiceWeek.week_number).all()

    if not weeks:
        raise HTTPException(status_code=404, detail=f"No weeks found for year {year}")

    week_ids = [w.id for w in weeks]

    # Build assignment map: week_id -> service_type -> [faculty_names]
    faculty_lookup = {f.id: f.name for f in db.query(Faculty).all()}
    assignments = db.query(ServiceWeekAssignment).filter(
        ServiceWeekAssignment.week_id.in_(week_ids)
    ).all()

    assign_map = {}  # (week_id, service_type) -> [names]
    for a in assignments:
        key = (a.week_id, a.service_type)
        name = faculty_lookup.get(a.faculty_id, a.faculty_id)
        assign_map.setdefault(key, []).append(name)

    # Build blocked map for annotation
    blocked_map = {}  # week_id -> set of faculty_ids
    for b in db.query(FacultyBlock).filter(FacultyBlock.week_id.in_(week_ids)).all():
        blocked_map.setdefault(b.week_id, set()).add(b.faculty_id)

    # Write CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "Week #", "Start Date", "End Date", "Week Type",
        "MICU 1", "MICU 2",
        "APP-ICU",
        "Procedures",
        "Consults",
        "Backup",
    ])

    for week in weeks:
        def get_slot(service, idx):
            names = assign_map.get((week.id, service), [])
            return names[idx] if idx < len(names) else ""

        writer.writerow([
            week.week_number,
            week.start_date.isoformat(),
            week.end_date.isoformat(),
            week.week_type,
            get_slot("MICU", 0),
            get_slot("MICU", 1),
            get_slot("APP-ICU", 0),
            get_slot("Procedures", 0),
            get_slot("Consults", 0),
            get_slot("Backup", 0),
        ])

    output.seek(0)
    filename = f"schedule-{year}-{year+1}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/service-schedule/export-inputs")
async def export_schedule_inputs_csv(
    year: int = 2026,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """
    Export faculty unavailability requests and volunteer requests as CSV files
    bundled into a ZIP archive — one file per input type.
    Useful for auditing schedule inputs and cross-referencing against the
    generated schedule to verify all rules were honored.
    """
    import zipfile
    from backend.models import (
        ServiceWeek, UnavailabilityRequest, DraftWeekRequest
    )

    weeks = db.query(ServiceWeek).filter(ServiceWeek.year == year).order_by(ServiceWeek.week_number).all()
    week_ids = {w.id for w in weeks}
    week_map = {w.id: w for w in weeks}
    faculty_map = {f.id: f.name for f in db.query(Faculty).all()}

    # ── Unavailability CSV ────────────────────────────────────────────────────
    unavail_out = io.StringIO()
    unavail_writer = csv.writer(unavail_out)
    unavail_writer.writerow(["Faculty ID", "Faculty Name", "Week #", "Week Label", "Start Date", "End Date", "Source", "Status"])

    # From UnavailabilityRequest table
    for req in db.query(UnavailabilityRequest).filter(
        UnavailabilityRequest.week_id.in_(week_ids)
    ).order_by(UnavailabilityRequest.faculty_id).all():
        w = week_map.get(req.week_id)
        if not w:
            continue
        unavail_writer.writerow([
            req.faculty_id,
            faculty_map.get(req.faculty_id, req.faculty_id),
            w.week_number,
            w.label,
            w.start_date.isoformat(),
            w.end_date.isoformat(),
            "UnavailabilityRequest",
            req.status or "unavailable"
        ])

    # From DraftWeekRequest (unavailable type)
    for dr in db.query(DraftWeekRequest).filter(
        DraftWeekRequest.week_id.in_(week_ids),
        DraftWeekRequest.request_type == "unavailable"
    ).order_by(DraftWeekRequest.faculty_id).all():
        w = week_map.get(dr.week_id)
        if not w:
            continue
        unavail_writer.writerow([
            dr.faculty_id,
            faculty_map.get(dr.faculty_id, dr.faculty_id),
            w.week_number,
            w.label,
            w.start_date.isoformat(),
            w.end_date.isoformat(),
            "DraftWeekRequest",
            "unavailable"
        ])

    # ── Volunteer CSV ─────────────────────────────────────────────────────────
    volunteer_out = io.StringIO()
    vol_writer = csv.writer(volunteer_out)
    vol_writer.writerow(["Faculty ID", "Faculty Name", "Week #", "Week Label", "Start Date", "End Date", "Submitted At"])

    for dr in db.query(DraftWeekRequest).filter(
        DraftWeekRequest.week_id.in_(week_ids),
        DraftWeekRequest.request_type == "volunteer"
    ).order_by(DraftWeekRequest.faculty_id).all():
        w = week_map.get(dr.week_id)
        if not w:
            continue
        vol_writer.writerow([
            dr.faculty_id,
            faculty_map.get(dr.faculty_id, dr.faculty_id),
            w.week_number,
            w.label,
            w.start_date.isoformat(),
            w.end_date.isoformat(),
            dr.submitted_at.isoformat() if dr.submitted_at else ""
        ])

    # ── Bundle into ZIP ───────────────────────────────────────────────────────
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"unavailability-{year}-{year+1}.csv", unavail_out.getvalue())
        zf.writestr(f"volunteers-{year}-{year+1}.csv", volunteer_out.getvalue())

    zip_buffer.seek(0)
    filename = f"schedule-inputs-{year}-{year+1}.zip"
    return StreamingResponse(
        iter([zip_buffer.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/service-schedule/export-faculty-grid")
async def export_faculty_grid_csv(
    year: int = 2026,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """
    Export a faculty-week grid CSV for human review.

    Columns: Week #, Start Date, End Date, Week Type, then one column per
    active faculty member (sorted by last name).

    Cell values:
      - The service abbreviation if assigned (MICU, APP-ICU, Procedures, Consults, Backup)
      - "Unavailable" if the faculty submitted unavailability for that week
      - "Open" if no assignment and not unavailable
    """
    from backend.models import ServiceWeek, ServiceWeekAssignment, UnavailabilityRequest, DraftWeekRequest, FacultyBlock

    # All active faculty sorted by last name then first name
    all_faculty = db.query(Faculty).filter(Faculty.active == True).order_by(Faculty.name).all()
    # Sort by last name token
    all_faculty_sorted = sorted(all_faculty, key=lambda f: (f.name.split()[-1].lower(), f.name.lower()))

    weeks = db.query(ServiceWeek).filter(
        ServiceWeek.year == year
    ).order_by(ServiceWeek.week_number).all()

    if not weeks:
        raise HTTPException(status_code=404, detail=f"No weeks found for year {year}")

    week_ids = [w.id for w in weeks]

    # Assignment map: (week_id, faculty_id) -> service label
    assignments = db.query(ServiceWeekAssignment).filter(
        ServiceWeekAssignment.week_id.in_(week_ids)
    ).all()
    assign_map = {}  # (week_id, faculty_id) -> service_type
    for a in assignments:
        assign_map[(a.week_id, a.faculty_id)] = a.service_type

    # Unavailability map: week_id -> set of faculty_ids
    unavail_set = set()
    for req in db.query(UnavailabilityRequest).filter(
        UnavailabilityRequest.status == "unavailable"
    ).all():
        if req.week_id in {w.id for w in weeks}:
            unavail_set.add((req.week_id, req.faculty_id))

    # Also include DraftWeekRequest unavailability
    for dr in db.query(DraftWeekRequest).filter(
        DraftWeekRequest.week_id.in_(week_ids),
        DraftWeekRequest.request_type == "unavailable"
    ).all():
        unavail_set.add((dr.week_id, dr.faculty_id))

    # FacultyBlock map: week_id -> set of faculty_ids (show as "Blocked")
    block_set = set()
    for b in db.query(FacultyBlock).filter(FacultyBlock.week_id.in_(week_ids)).all():
        block_set.add((b.week_id, b.faculty_id))

    output = io.StringIO()
    writer = csv.writer(output)

    # Header row: Week #, Start Date, End Date, Week Type, then faculty names
    header = ["Week #", "Start Date", "End Date", "Week Type"] + [f.name for f in all_faculty_sorted]
    writer.writerow(header)

    for week in weeks:
        row = [
            week.week_number,
            week.start_date.isoformat(),
            week.end_date.isoformat(),
            week.week_type,
        ]
        for f in all_faculty_sorted:
            key = (week.id, f.id)
            if key in assign_map:
                row.append(assign_map[key])
            elif key in block_set:
                row.append("Blocked")
            elif key in unavail_set:
                row.append("Unavailable")
            else:
                row.append("Open")
        writer.writerow(row)

    output.seek(0)
    filename = f"faculty-grid-{year}-{year+1}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.delete("/service-schedule/auto-only")
async def clear_auto_generated_schedule(
    year: int = 2026,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """
    Clear ONLY auto-generated assignments for a year.
    Manual (is_manual=True) and imported (imported=True) assignments are preserved.
    Use this to see a clean slate of only what was manually set or imported from CSV.
    """
    from backend.models import ServiceWeek, ServiceWeekAssignment

    weeks = db.query(ServiceWeek).filter(ServiceWeek.year == year).all()
    week_ids = [w.id for w in weeks]

    deleted = db.query(ServiceWeekAssignment).filter(
        ServiceWeekAssignment.week_id.in_(week_ids),
        ServiceWeekAssignment.is_manual == False,
        ServiceWeekAssignment.imported == False
    ).delete(synchronize_session=False)

    db.commit()

    return {
        "success": True,
        "assignments_deleted": deleted,
        "preserved": "manual and imported assignments untouched",
        "year": year
    }


@router.delete("/service-schedule")
async def clear_service_schedule(
    year: int = 2026,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """
    Clear ALL service assignments for a year (manual, imported, and auto-generated).
    """
    from backend.models import ServiceWeek, ServiceWeekAssignment

    weeks = db.query(ServiceWeek).filter(ServiceWeek.year == year).all()
    week_ids = [w.id for w in weeks]

    deleted = db.query(ServiceWeekAssignment).filter(
        ServiceWeekAssignment.week_id.in_(week_ids)
    ).delete(synchronize_session=False)

    db.commit()

    return {
        "success": True,
        "assignments_deleted": deleted,
        "year": year
    }
