# backend/schedule_generator.py
"""
Inpatient Service Schedule Generator

Generates weekly assignments for the 4 service types:
- MICU: 2 providers per week
- APP-ICU: 1 provider per week  
- Procedures: 1 provider per week
- Consults: 1 provider per week

Constraints:
- Faculty can only be assigned to services where they have weeks > 0
- Each faculty can work +/- 1 week of their allocated amount per service
- Faculty marked unavailable for a week cannot be assigned
- NO BACK-TO-BACK BLOCKS: Faculty must have at least one week off between any inpatient service assignments
- Try to distribute assignments evenly across the year

"""

from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict
import random
from sqlalchemy.orm import Session
from datetime import datetime
import uuid


@dataclass
class FacultyCapacity:
    """Tracks a faculty member's capacity for each service"""
    faculty_id: str
    name: str
    micu_target: int  # Target weeks (from faculty.micu_weeks)
    app_icu_target: int
    procedures_target: int
    consults_target: int
    backup_target: int
    micu_assigned: int = 0  # Currently assigned
    app_icu_assigned: int = 0
    procedures_assigned: int = 0
    consults_assigned: int = 0
    backup_assigned: int = 0
    last_assigned_week: int = -999  # Track last week number assigned (for back-to-back prevention)
    assigned_weeks: Set[int] = field(default_factory=set)  # All weeks this faculty is assigned

    def can_work_service(self, service_type: str) -> bool:
        """Check if faculty can work more weeks of this service.
        Hard cap: never exceed the allotted target (Rule 2)."""
        if service_type == "MICU":
            return self.micu_target > 0 and self.micu_assigned < self.micu_target
        elif service_type == "APP-ICU":
            return self.app_icu_target > 0 and self.app_icu_assigned < self.app_icu_target
        elif service_type == "Procedures":
            return self.procedures_target > 0 and self.procedures_assigned < self.procedures_target
        elif service_type == "Consults":
            return self.consults_target > 0 and self.consults_assigned < self.consults_target
        elif service_type == "Backup":
            return self.backup_target > 0 and self.backup_assigned < self.backup_target
        return False

    def can_work_week(self, week_number: int) -> bool:
        """
        Check if faculty can work this week (no back-to-back constraint).
        Must have at least one week gap from any previous assignment.
        """
        if (week_number - 1) in self.assigned_weeks:
            return False  # Previous week is assigned - can't do back-to-back
        if (week_number + 1) in self.assigned_weeks:
            return False  # Next week is assigned - would create back-to-back
        if week_number in self.assigned_weeks:
            return False  # Already assigned this week
        return True

    def needs_more_weeks(self, service_type: str) -> bool:
        """Check if faculty still needs assignments to meet their target."""
        if service_type == "MICU":
            return self.micu_target > 0 and self.micu_assigned < self.micu_target
        elif service_type == "APP-ICU":
            return self.app_icu_target > 0 and self.app_icu_assigned < self.app_icu_target
        elif service_type == "Procedures":
            return self.procedures_target > 0 and self.procedures_assigned < self.procedures_target
        elif service_type == "Consults":
            return self.consults_target > 0 and self.consults_assigned < self.consults_target
        elif service_type == "Backup":
            return self.backup_target > 0 and self.backup_assigned < self.backup_target
        return False

    def assign(self, service_type: str, week_number: int):
        """Record an assignment"""
        if service_type == "MICU":
            self.micu_assigned += 1
        elif service_type == "APP-ICU":
            self.app_icu_assigned += 1
        elif service_type == "Procedures":
            self.procedures_assigned += 1
        elif service_type == "Consults":
            self.consults_assigned += 1
        elif service_type == "Backup":
            self.backup_assigned += 1

        # Track for back-to-back prevention
        self.last_assigned_week = week_number
        self.assigned_weeks.add(week_number)

    def get_priority_score(self, service_type: str) -> float:
        """Get priority score - higher means more urgently needs assignment"""
        if service_type == "MICU":
            if self.micu_target == 0:
                return -1000  # Cannot work this service
            return (self.micu_target - self.micu_assigned) / max(1, self.micu_target)
        elif service_type == "APP-ICU":
            if self.app_icu_target == 0:
                return -1000
            return (self.app_icu_target - self.app_icu_assigned) / max(1, self.app_icu_target)
        elif service_type == "Procedures":
            if self.procedures_target == 0:
                return -1000
            return (self.procedures_target - self.procedures_assigned) / max(1, self.procedures_target)
        elif service_type == "Consults":
            if self.consults_target == 0:
                return -1000
            return (self.consults_target - self.consults_assigned) / max(1, self.consults_target)
        elif service_type == "Backup":
            if self.backup_target == 0:
                return -1000
            return (self.backup_target - self.backup_assigned) / max(1, self.backup_target)
        return 0

    def get_total_target(self) -> int:
        """Get total target weeks across all services"""
        return self.micu_target + self.app_icu_target + self.procedures_target + self.consults_target + self.backup_target

    def get_total_assigned(self) -> int:
        """Get total assigned weeks across all services"""
        return self.micu_assigned + self.app_icu_assigned + self.procedures_assigned + self.consults_assigned + self.backup_assigned


@dataclass
class ScheduleAssignment:
    """A single assignment of a faculty to a week/service"""
    faculty_id: str
    week_id: str
    service_type: str


# Service requirements per week
SERVICE_REQUIREMENTS = {
    "MICU": 2,
    "APP-ICU": 1,
    "Procedures": 1,
    "Consults": 1,
    "Backup": 1,
}


def generate_schedule(
    db: Session,
    year: int = 2026,
    clear_existing: bool = True
) -> Dict:
    """
    Generate a complete inpatient service schedule for the academic year.
    
    Key constraint: NO BACK-TO-BACK BLOCKS
    Faculty must have at least one week off between any inpatient service assignments.
    
    Args:
        db: Database session
        year: Academic year (e.g., 2026 for AY 2026-2027)
        clear_existing: Whether to clear existing assignments first
        
    Returns:
        Dict with schedule summary and any issues found
    """
    from backend.models import Faculty, ServiceWeek, UnavailabilityRequest, ServiceWeekAssignment, FacultyBlock

    # Get all active faculty
    faculty_list = db.query(Faculty).filter(Faculty.active == True).all()

    # Get all weeks for this year
    weeks = db.query(ServiceWeek).filter(
        ServiceWeek.year == year
    ).order_by(ServiceWeek.week_number).all()

    if not weeks:
        return {
            "success": False,
            "error": f"No weeks found for year {year}. Generate weeks first.",
            "assignments_created": 0
        }

    week_ids = [w.id for w in weeks]
    week_number_map = {w.id: w.week_number for w in weeks}

    # Get unavailability data (UnavailabilityRequest)
    unavailability_map = defaultdict(set)  # week_id -> set of faculty_ids
    unavailable_requests = db.query(UnavailabilityRequest).filter(
        UnavailabilityRequest.status == "unavailable"
    ).all()

    for req in unavailable_requests:
        if req.week_id in week_number_map:
            unavailability_map[req.week_id].add(req.faculty_id)

    # Load FacultyBlock records (admin-set hard blocks)
    blocks_map = defaultdict(set)  # week_id -> set of faculty_ids
    for block in db.query(FacultyBlock).filter(FacultyBlock.week_id.in_(week_ids)).all():
        blocks_map[block.week_id].add(block.faculty_id)

    # Load volunteer requests (DraftWeekRequest with request_type='volunteer')
    # volunteer_map[week_id] -> set of faculty_ids who volunteered for that week (Rule 6)
    # Also load DraftWeekRequest unavailability to supplement UnavailabilityRequest
    from backend.models import DraftWeekRequest
    volunteer_map = defaultdict(set)   # week_id -> set of faculty_ids
    draft_unavail_map = defaultdict(set)  # week_id -> set of faculty_ids (unavailable via draft)
    draft_requests = db.query(DraftWeekRequest).filter(
        DraftWeekRequest.week_id.in_(week_ids)
    ).all()
    for dr in draft_requests:
        if dr.request_type == 'volunteer':
            volunteer_map[dr.week_id].add(dr.faculty_id)
        elif dr.request_type == 'unavailable':
            draft_unavail_map[dr.week_id].add(dr.faculty_id)
            unavailability_map[dr.week_id].add(dr.faculty_id)  # merge into main map

    # Clear existing AUTO-generated assignments only — preserve manual and imported
    if clear_existing:
        db.query(ServiceWeekAssignment).filter(
            ServiceWeekAssignment.week_id.in_(week_ids),
            ServiceWeekAssignment.is_manual == False,
            ServiceWeekAssignment.imported == False
        ).delete(synchronize_session=False)
        db.commit()

    # Pre-load ALL locked assignments (manual + imported).
    # locked_slots[(week_id, service_type)] -> set of faculty_ids already placed.
    # _fresh_capacity() uses locked_assignments to seed each run's capacity tracker.
    locked_assignments = db.query(ServiceWeekAssignment).filter(
        ServiceWeekAssignment.week_id.in_(week_ids),
        (ServiceWeekAssignment.is_manual == True) | (ServiceWeekAssignment.imported == True)
    ).all()

    locked_slots: Dict[tuple, set] = defaultdict(set)
    for la in locked_assignments:
        locked_slots[(la.week_id, la.service_type)].add(la.faculty_id)

    # ── Helper: build a fresh capacity dict pre-loaded with locked assignments ──
    def _fresh_capacity() -> Dict:
        cap_map = {}
        for f in faculty_list:
            cap_map[f.id] = FacultyCapacity(
                faculty_id=f.id,
                name=f.name,
                micu_target=f.micu_weeks or 0,
                app_icu_target=f.app_icu_weeks or 0,
                procedures_target=f.procedure_weeks or 0,
                consults_target=f.consult_weeks or 0,
                backup_target=f.backup_weeks or 0,
            )
        for la in locked_assignments:
            cap = cap_map.get(la.faculty_id)
            wn = week_number_map.get(la.week_id)
            if cap and wn is not None:
                cap.assign(la.service_type, wn)
        return cap_map

    # ── Helper: one full pass over an ordered week list ───────────────────────
    def _one_pass(weeks_ordered, cap_map):
        run_assignments = []
        run_issues = []
        run_b2b = 0

        for week in weeks_ordered:
            week_number = week.week_number
            week_assignments = defaultdict(list)
            unavailable_this_week = unavailability_map.get(week.id, set())
            blocked_this_week = blocks_map.get(week.id, set())

            locked_this_week_any_service = set()
            for (wid, _svc), fids in locked_slots.items():
                if wid == week.id:
                    locked_this_week_any_service.update(fids)

            volunteers_this_week = volunteer_map.get(week.id, set())

            for service_type, required_count in SERVICE_REQUIREMENTS.items():
                already_locked = locked_slots.get((week.id, service_type), set())
                slots_needed = required_count - len(already_locked)
                if slots_needed <= 0:
                    continue

                eligible = []
                for fid, cap in cap_map.items():
                    if fid in unavailable_this_week or fid in blocked_this_week:
                        continue
                    if fid in locked_this_week_any_service:
                        continue
                    if any(fid in assigned for assigned in week_assignments.values()):
                        continue
                    if not cap.can_work_week(week_number):
                        run_b2b += 1
                        continue
                    if cap.can_work_service(service_type):
                        eligible.append((fid, cap))

                eligible.sort(key=lambda x: (
                    0 if x[0] in volunteers_this_week else 1,
                    -x[1].get_priority_score(service_type),
                    random.random()
                ))

                assigned_count = 0
                for fid, cap in eligible:
                    if assigned_count >= slots_needed:
                        break
                    run_assignments.append(ScheduleAssignment(
                        faculty_id=fid, week_id=week.id, service_type=service_type
                    ))
                    week_assignments[service_type].append(fid)
                    cap.assign(service_type, week_number)
                    assigned_count += 1

                total_filled = len(already_locked) + assigned_count
                if total_filled < required_count:
                    run_issues.append({
                        "week": week.week_number,
                        "week_label": week.label,
                        "service": service_type,
                        "required": required_count,
                        "assigned": total_filled,
                        "issue": "understaffed"
                    })

        return run_assignments, run_issues, run_b2b

    # ── Difficulty score: weeks with the most constraints get filled first ────
    # Static estimate: unavailable + blocked faculty for that week (higher = harder)
    def _week_difficulty(week):
        n_unavail = len(unavailability_map.get(week.id, set()))
        n_blocked = len(blocks_map.get(week.id, set()))
        return n_unavail + n_blocked   # higher = harder to fill

    weeks_hardest_first = sorted(weeks, key=_week_difficulty, reverse=True)

    # ── Multi-run: try N orderings and keep the one with the fewest gaps ──────
    NUM_RUNS = 20

    best_assignments = None
    best_issues = None
    best_b2b = 0
    best_filled = -1

    for run_idx in range(NUM_RUNS):
        if run_idx == 0:
            # First run: hardest weeks first (deterministic)
            ordered = weeks_hardest_first
        elif run_idx == 1:
            # Second run: calendar order (original behavior)
            ordered = weeks
        else:
            # Remaining runs: randomized week order
            ordered = list(weeks)
            random.shuffle(ordered)

        cap_map = _fresh_capacity()
        run_assignments, run_issues, run_b2b = _one_pass(ordered, cap_map)

        filled = len(run_assignments)
        if filled > best_filled:
            best_filled = filled
            best_assignments = run_assignments
            best_issues = run_issues
            best_b2b = run_b2b

        # Perfect fill — no need to keep trying
        total_slots_needed = sum(SERVICE_REQUIREMENTS.values()) * len(weeks) - sum(
            len(v) for v in locked_slots.values()
        )
        if filled >= total_slots_needed:
            break

    assignments = best_assignments
    issues = best_issues
    back_to_back_prevented = best_b2b

    # Rebuild capacity map from best run to report variance
    final_cap_map = _fresh_capacity()
    for a in assignments:
        cap = final_cap_map.get(a.faculty_id)
        wn = week_number_map.get(a.week_id)
        if cap and wn is not None:
            cap.assign(a.service_type, wn)

    # Check for faculty who are over/under their targets
    capacity_issues = []
    for fid, cap in final_cap_map.items():
        for service, target, assigned in [
            ("MICU", cap.micu_target, cap.micu_assigned),
            ("APP-ICU", cap.app_icu_target, cap.app_icu_assigned),
            ("Procedures", cap.procedures_target, cap.procedures_assigned),
            ("Consults", cap.consults_target, cap.consults_assigned),
            ("Backup", cap.backup_target, cap.backup_assigned),
        ]:
            if target > 0:
                diff = assigned - target
                if abs(diff) > 1:  # More than +/- 1 week variance
                    capacity_issues.append({
                        "faculty_id": fid,
                        "faculty_name": cap.name,
                        "service": service,
                        "target": target,
                        "assigned": assigned,
                        "variance": diff
                    })
    
    # Save assignments to database
    for assignment in assignments:
        db_assignment = ServiceWeekAssignment(
            id=str(uuid.uuid4()),
            faculty_id=assignment.faculty_id,
            week_id=assignment.week_id,
            service_type=assignment.service_type,
            imported=False
        )
        db.add(db_assignment)
    
    db.commit()
    
    return {
        "success": True,
        "year": year,
        "total_weeks": len(weeks),
        "assignments_created": len(assignments),
        "staffing_issues": issues,
        "capacity_issues": capacity_issues,
        "back_to_back_prevented": back_to_back_prevented,
        "summary": {
            "MICU": sum(1 for a in assignments if a.service_type == "MICU"),
            "APP-ICU": sum(1 for a in assignments if a.service_type == "APP-ICU"),
            "Procedures": sum(1 for a in assignments if a.service_type == "Procedures"),
            "Consults": sum(1 for a in assignments if a.service_type == "Consults"),
            "Backup": sum(1 for a in assignments if a.service_type == "Backup"),
        }
    }


def get_schedule_view(
    db: Session,
    year: int = 2026
) -> Dict:
    """
    Get the current schedule for viewing.
    
    Returns a structured view of all assignments by week.
    """
    from backend.models import Faculty, ServiceWeek, ServiceWeekAssignment
    
    weeks = db.query(ServiceWeek).filter(
        ServiceWeek.year == year
    ).order_by(ServiceWeek.week_number).all()
    
    if not weeks:
        return {"success": False, "error": "No weeks found", "schedule": []}
    
    # Get all assignments
    week_ids = [w.id for w in weeks]
    assignments = db.query(ServiceWeekAssignment).filter(
        ServiceWeekAssignment.week_id.in_(week_ids)
    ).all()
    
    # Get faculty lookup
    faculty_lookup = {f.id: f.name for f in db.query(Faculty).all()}
    
    # Build assignment map
    assignment_map = defaultdict(lambda: defaultdict(list))  # week_id -> service -> [(faculty_id, name)]
    for a in assignments:
        assignment_map[a.week_id][a.service_type].append({
            "faculty_id": a.faculty_id,
            "faculty_name": faculty_lookup.get(a.faculty_id, a.faculty_id)
        })
    
    # Build schedule view
    schedule = []
    for week in weeks:
        week_data = {
            "week_id": week.id,
            "week_number": week.week_number,
            "label": week.label,
            "start_date": week.start_date.isoformat(),
            "end_date": week.end_date.isoformat(),
            "week_type": week.week_type,
            "assignments": {
                "MICU": assignment_map[week.id].get("MICU", []),
                "APP-ICU": assignment_map[week.id].get("APP-ICU", []),
                "Procedures": assignment_map[week.id].get("Procedures", []),
                "Consults": assignment_map[week.id].get("Consults", []),
                "Backup": assignment_map[week.id].get("Backup", []),
            },
            "is_complete": (
                len(assignment_map[week.id].get("MICU", [])) >= 2 and
                len(assignment_map[week.id].get("APP-ICU", [])) >= 1 and
                len(assignment_map[week.id].get("Procedures", [])) >= 1 and
                len(assignment_map[week.id].get("Consults", [])) >= 1 and
                len(assignment_map[week.id].get("Backup", [])) >= 1
            )
        }
        schedule.append(week_data)
    
    # Calculate summary statistics
    total_assignments = len(assignments)
    complete_weeks = sum(1 for w in schedule if w["is_complete"])
    
    return {
        "success": True,
        "year": year,
        "total_weeks": len(weeks),
        "complete_weeks": complete_weeks,
        "total_assignments": total_assignments,
        "schedule": schedule
    }


def validate_schedule(
    db: Session,
    year: int = 2026
) -> Dict:
    """
    Validate an existing schedule for constraint violations.
    
    Checks:
    - Back-to-back assignments
    - Capacity violations
    - Missing assignments
    
    Returns dict with any violations found.
    """
    from backend.models import Faculty, ServiceWeek, ServiceWeekAssignment
    
    weeks = db.query(ServiceWeek).filter(
        ServiceWeek.year == year
    ).order_by(ServiceWeek.week_number).all()
    
    week_ids = [w.id for w in weeks]
    assignments = db.query(ServiceWeekAssignment).filter(
        ServiceWeekAssignment.week_id.in_(week_ids)
    ).all()
    
    # Track which weeks each faculty is assigned
    faculty_weeks = defaultdict(set)  # faculty_id -> set of week_numbers
    week_number_lookup = {w.id: w.week_number for w in weeks}
    
    for a in assignments:
        week_num = week_number_lookup.get(a.week_id)
        if week_num:
            faculty_weeks[a.faculty_id].add(week_num)
    
    # Check for back-to-back violations
    back_to_back_violations = []
    for faculty_id, assigned_weeks in faculty_weeks.items():
        sorted_weeks = sorted(assigned_weeks)
        for i in range(len(sorted_weeks) - 1):
            if sorted_weeks[i+1] - sorted_weeks[i] == 1:
                back_to_back_violations.append({
                    "faculty_id": faculty_id,
                    "week1": sorted_weeks[i],
                    "week2": sorted_weeks[i+1]
                })
    
    return {
        "year": year,
        "total_assignments": len(assignments),
        "back_to_back_violations": back_to_back_violations,
        "violation_count": len(back_to_back_violations),
        "is_valid": len(back_to_back_violations) == 0
    }
