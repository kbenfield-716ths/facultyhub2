# backend/models.py
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Boolean, Date, DateTime, Float,
    ForeignKey, create_engine, text, Text, Index, UniqueConstraint
)
import json
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session
import os
import uuid

# Use persistent volume if available, fallback to local
db_path = "/data/staff.db" if os.path.exists("/data") else "./staff.db"
DATABASE_URL = f"sqlite:///{db_path}"

Base = declarative_base()
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

#===========================================
# SECURITY MODELS
#===========================================

class AuditLog(Base):
    """Audit log for tracking admin actions"""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    user_id = Column(String, nullable=False, index=True)
    user_name = Column(String, nullable=False)
    action = Column(String, nullable=False, index=True)
    resource_type = Column(String, nullable=True, index=True)
    resource_id = Column(String, nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    
    __table_args__ = (
        Index('ix_audit_logs_timestamp_user', 'timestamp', 'user_id'),
        Index('ix_audit_logs_action_resource', 'action', 'resource_type'),
    )


class SessionToken(Base):
    """Enhanced session management with timeout tracking"""
    __tablename__ = "session_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, unique=True, nullable=False, index=True)
    faculty_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_activity = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    invalidated = Column(Boolean, default=False)
    invalidated_at = Column(DateTime, nullable=True)
    impersonated_by = Column(String, nullable=True)  # admin faculty_id if this is an impersonation session


class PasswordResetToken(Base):
    """Tokens for password reset functionality"""
    __tablename__ = "password_reset_tokens"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    faculty_id = Column(String, nullable=False, index=True)
    token = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    used_at = Column(DateTime, nullable=True)


# ==========================================
# DIVISIONS
# ==========================================

class Division(Base):
    """
    One group inside the department — PCCM, MICU APPs, Hospitalists, etc.
    All users live in the single faculty table with a division_key flag;
    each division decides its own scheduling style via rotations config.
    """
    __tablename__ = "divisions"

    key        = Column(String, primary_key=True)      # "pccm", "micu_app"
    label      = Column(String, nullable=False)        # "PCCM"
    color      = Column(String, nullable=True)
    is_active  = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ==========================================
# KNOWLEDGE BASE
# ==========================================

class KnowledgeBaseArticle(Base):
    __tablename__ = "knowledge_base_articles"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    description = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String, nullable=False)
    
    is_published = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)

    # null = visible department-wide; set = policies for one division only
    division_key = Column(String, ForeignKey("divisions.key"), nullable=True, index=True)
    
    created_by = Column(String, ForeignKey("faculty.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    author = relationship("Faculty", foreign_keys=[created_by])


# ==========================================
# DRAFT SYSTEM
# ==========================================

class DraftRound(Base):
    __tablename__ = "draft_rounds"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    year = Column(Integer, nullable=False)
    round_number = Column(Integer, default=1)
    status = Column(String, default='pending')
    window_size = Column(Integer, default=5)
    hours_per_slot = Column(Integer, default=72)
    
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    slots = relationship("DraftSlot", back_populates="draft_round", cascade="all, delete-orphan")


class DraftSlot(Base):
    __tablename__ = "draft_slots"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    round_id = Column(String, ForeignKey("draft_rounds.id"), nullable=False)
    faculty_id = Column(String, ForeignKey("faculty.id"), nullable=False)
    priority_order = Column(Integer, nullable=False)
    
    status = Column(String, default='waiting')
    notified_at = Column(DateTime, nullable=True)
    deadline = Column(DateTime, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    draft_round = relationship("DraftRound", back_populates="slots")
    faculty = relationship("Faculty")


# ==========================================
# MOONLIGHTING MODELS
# ==========================================


class Month(Base):
    __tablename__ = "months"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    
    shifts = relationship("Shift", back_populates="month")


class Shift(Base):
    """Moonlighting night shifts"""
    __tablename__ = "shifts"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    month_id = Column(Integer, ForeignKey("months.id"), nullable=False)
    date = Column(Date, nullable=False)
    slots = Column(Integer, default=1)
    
    month = relationship("Month", back_populates="shifts")
    signups = relationship("Signup", back_populates="shift")
    assignments = relationship("Assignment", back_populates="shift")


class Signup(Base):
    """Faculty requests for moonlighting shifts"""
    __tablename__ = "signups"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    provider_id = Column(String, ForeignKey("faculty.id"), nullable=False, index=True)
    shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=False, index=True)
    desired_nights = Column(Integer, nullable=False)
    locked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    provider = relationship("Faculty", foreign_keys=[provider_id])
    shift = relationship("Shift", back_populates="signups")


class Assignment(Base):
    """Final moonlighting shift assignments"""
    __tablename__ = "assignments"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    provider_id = Column(String, ForeignKey("faculty.id"), nullable=False)
    shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    provider = relationship("Faculty", foreign_keys=[provider_id])
    shift = relationship("Shift", back_populates="assignments")


# ==========================================
# FACULTY MODEL (UNIFIED WITH SECURITY FIELDS)
# ==========================================

class Faculty(Base):
    """Faculty member with scheduling profile and authentication"""
    __tablename__ = "faculty"
    
    # Core identity (UVA computing ID: "KE4Z", "IN2C", etc.)
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False)
    
    # Authentication (existing)
    password_hash = Column(String)
    password_changed = Column(Boolean, default=False)
    registered = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    
    # NEW SECURITY FIELDS
    password_reset_required = Column(Boolean, default=False)
    password_last_changed = Column(DateTime, nullable=True)
    failed_login_attempts = Column(Integer, default=0)
    account_locked_until = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    last_login_ip = Column(String, nullable=True)
    
    active = Column(Boolean, default=True)

    # Which division this user belongs to (null = unassigned; admins see all)
    division_key = Column(String, ForeignKey("divisions.key"), nullable=True, index=True)

    # Moonlighting participation (feature-flagged via instance_config)
    moonlighter = Column(Boolean, default=False, nullable=False)
    draft_exempt = Column(Boolean, default=False, nullable=False)
    moonlighting_priority = Column(Integer, default=2, nullable=False)  # 1=high, 2=medium, 3=low

    # Group-specific attributes — stored as JSON, defined by instance_config faculty_attributes
    extra_config = Column(Text, default='{}', nullable=False)

    # Relationships
    unavailability_requests = relationship("UnavailabilityRequest", back_populates="faculty")
    service_assignments = relationship("ServiceWeekAssignment", back_populates="faculty", foreign_keys="ServiceWeekAssignment.faculty_id")
    moonlighting_signups = relationship("Signup", foreign_keys="Signup.provider_id")
    moonlighting_assignments = relationship("Assignment", foreign_keys="Assignment.provider_id")

    # ── Convenience accessors for extra_config fields ──────────────────────
    def get_extra(self, key, default=None):
        """Read a value from the extra_config JSON blob."""
        try:
            return json.loads(self.extra_config or '{}').get(key, default)
        except (json.JSONDecodeError, TypeError):
            return default

    def set_extra(self, key, value, db_session=None):
        """Write a value into the extra_config JSON blob."""
        try:
            config = json.loads(self.extra_config or '{}')
        except (json.JSONDecodeError, TypeError):
            config = {}
        config[key] = value
        self.extra_config = json.dumps(config)

    # Properties so legacy routes that reference .base_points / .bonus_points
    # continue to work — values now live in extra_config.
    @property
    def base_points(self):
        return self.get_extra('base_points', 0)

    @base_points.setter
    def base_points(self, value):
        self.set_extra('base_points', value)

    @property
    def bonus_points(self):
        return self.get_extra('bonus_points', 0)

    @bonus_points.setter
    def bonus_points(self, value):
        self.set_extra('bonus_points', value)

    @property
    def does_moonlighting(self):
        """Alias for moonlighter field — used by message board access control."""
        return self.moonlighter

    @does_moonlighting.setter
    def does_moonlighting(self, value):
        self.moonlighter = value


# ==========================================
# SERVICE SCHEDULING MODELS
# ==========================================

class ServiceWeek(Base):
    """The 52 weeks of the academic year for service availability scheduling"""
    __tablename__ = "service_weeks"
    
    id = Column(String, primary_key=True, index=True)
    week_number = Column(Integer, nullable=False)
    label = Column(String, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    year = Column(Integer, nullable=False)
    
    week_type = Column(String, default="regular")
    point_cost_off = Column(Integer, default=5)
    point_reward_work = Column(Integer, default=0)
    min_staff_required = Column(Integer, default=5)
    
    historic_unavailable_count = Column(Integer, default=0)
    
    unavailability_requests = relationship("UnavailabilityRequest", back_populates="week")
    service_assignments = relationship("ServiceWeekAssignment", back_populates="week")


class UnavailabilityRequest(Base):
    """Faculty unavailability requests for specific weeks"""
    __tablename__ = "unavailability_requests"

    id = Column(String, primary_key=True, index=True)
    faculty_id = Column(String, ForeignKey('faculty.id'), nullable=False, index=True)
    week_id = Column(String, ForeignKey('service_weeks.id'), nullable=False, index=True)

    status = Column(String, nullable=False, default="unavailable")

    points_spent = Column(Integer, default=0)
    points_earned = Column(Integer, default=0)

    gives_priority = Column(Boolean, default=False)

    service_preference = Column(Text, nullable=True)  # Optional preference for service type

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    faculty = relationship("Faculty", back_populates="unavailability_requests")
    week = relationship("ServiceWeek", back_populates="unavailability_requests")


class ServiceWeekAssignment(Base):
    """Actual service week assignments (MICU, APP-ICU, Procedures, Consults)"""
    __tablename__ = "service_week_assignments"

    id = Column(String, primary_key=True, index=True)
    faculty_id = Column(String, ForeignKey('faculty.id'), nullable=False, index=True)
    week_id = Column(String, ForeignKey('service_weeks.id'), nullable=False, index=True)

    service_type = Column(String, nullable=False, index=True)

    imported = Column(Boolean, default=False)
    is_manual = Column(Boolean, default=False)  # True if manually assigned by admin
    reason = Column(Text)  # Reason for manual assignment
    created_by = Column(String, ForeignKey('faculty.id'))  # Admin who created manual assignment

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    faculty = relationship("Faculty", back_populates="service_assignments", foreign_keys=[faculty_id])
    week = relationship("ServiceWeek", back_populates="service_assignments")
    created_by_faculty = relationship("Faculty", foreign_keys=[created_by])


class FacultyBlock(Base):
    """
    Blocks faculty from being assigned to specific weeks.
    Used for remote faculty, sabbaticals, or other situations where faculty cannot do in-person service.
    """
    __tablename__ = "faculty_blocks"

    id = Column(String, primary_key=True, index=True)
    faculty_id = Column(String, ForeignKey('faculty.id'), nullable=False, index=True)
    week_id = Column(String, ForeignKey('service_weeks.id'), nullable=False, index=True)

    reason = Column(Text)  # e.g., "Remote faculty - cannot do in-person services"
    created_by = Column(String, ForeignKey('faculty.id'))  # Admin who created the block

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    faculty = relationship("Faculty", foreign_keys=[faculty_id])
    week = relationship("ServiceWeek")
    created_by_faculty = relationship("Faculty", foreign_keys=[created_by])


# ==========================================
# MESSAGE BOARDS
# ==========================================

class MessageBoard(Base):
    """Message boards (General, Moonlighting, etc.)"""
    __tablename__ = "message_boards"
    
    id = Column(String, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    icon = Column(String(10))
    requires_moonlighting = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    messages = relationship("Message", back_populates="board", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<MessageBoard(id={self.id}, name={self.name})>"


class Message(Base):
    """Messages (threads and replies)"""
    __tablename__ = "messages"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    board_id = Column(String, ForeignKey("message_boards.id", ondelete="CASCADE"), nullable=False)
    author_id = Column(String, ForeignKey("faculty.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(String, ForeignKey("messages.id", ondelete="CASCADE"), nullable=True)
    
    subject = Column(Text)
    content = Column(Text, nullable=False)
    is_pinned = Column(Boolean, default=False)
    is_edited = Column(Boolean, default=False)
    edited_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    board = relationship("MessageBoard", back_populates="messages")
    author = relationship("Faculty", foreign_keys=[author_id])
    parent = relationship("Message", remote_side=[id], backref="replies")
    reactions = relationship("MessageReaction", back_populates="message", cascade="all, delete-orphan")
    read_status = relationship("MessageReadStatus", back_populates="message", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_messages_board', 'board_id'),
        Index('idx_messages_author', 'author_id'),
        Index('idx_messages_parent', 'parent_id'),
        Index('idx_messages_created', 'created_at'),
    )
    
    def __repr__(self):
        return f"<Message(id={self.id}, author={self.author_id}, board={self.board_id})>"


class MessageReaction(Base):
    """Emoji reactions to messages"""
    __tablename__ = "message_reactions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id = Column(String, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    faculty_id = Column(String, ForeignKey("faculty.id", ondelete="CASCADE"), nullable=False)
    reaction = Column(String(10), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    message = relationship("Message", back_populates="reactions")
    faculty = relationship("Faculty")
    
    __table_args__ = (
        Index('idx_reactions_message', 'message_id'),
        Index('idx_reactions_unique', 'message_id', 'faculty_id', 'reaction', unique=True),
    )
    
    def __repr__(self):
        return f"<MessageReaction(message={self.message_id}, faculty={self.faculty_id}, reaction={self.reaction})>"


class MessageReadStatus(Base):
    """Track which messages faculty have read"""
    __tablename__ = "message_read_status"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id = Column(String, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    faculty_id = Column(String, ForeignKey("faculty.id", ondelete="CASCADE"), nullable=False)
    read_at = Column(DateTime, default=datetime.utcnow)
    
    message = relationship("Message", back_populates="read_status")
    faculty = relationship("Faculty")
    
    __table_args__ = (
        Index('idx_read_status_faculty', 'faculty_id'),
        Index('idx_read_status_message', 'message_id'),
        Index('idx_read_status_unique', 'message_id', 'faculty_id', unique=True),
    )
    
    def __repr__(self):
        return f"<MessageReadStatus(message={self.message_id}, faculty={self.faculty_id})>"


# ==========================================
# WAVE-BASED DRAFT SYSTEM
# ==========================================

class DraftWaveConfig(Base):
    """Configuration for wave-based draft system"""
    __tablename__ = "draft_wave_configs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    year = Column(Integer, nullable=False, unique=True)  # Academic year
    close_date = Column(DateTime, nullable=False)  # When all submissions close
    status = Column(String, default='pending')  # pending, active, closed

    created_at = Column(DateTime, default=datetime.utcnow)
    activated_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)

    waves = relationship("DraftWave", back_populates="config", cascade="all, delete-orphan")
    week_status = relationship("WeekDraftStatus", back_populates="config", cascade="all, delete-orphan")
    requests = relationship("DraftWeekRequest", back_populates="config", cascade="all, delete-orphan")


class DraftWave(Base):
    """Individual waves in the draft (e.g., Test Wave, Wednesday Wave)"""
    __tablename__ = "draft_waves"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    config_id = Column(String, ForeignKey("draft_wave_configs.id"), nullable=False)
    name = Column(String, nullable=False)  # e.g., "Test Wave", "Wednesday Wave"
    open_date = Column(DateTime, nullable=False)  # When this wave can start submitting
    wave_order = Column(Integer, nullable=False)  # Order of waves (1, 2, 3, etc.)

    created_at = Column(DateTime, default=datetime.utcnow)

    config = relationship("DraftWaveConfig", back_populates="waves")
    faculty_assignments = relationship("WaveFacultyAssignment", back_populates="wave", cascade="all, delete-orphan")


class WaveFacultyAssignment(Base):
    """Assigns faculty members to specific waves"""
    __tablename__ = "wave_faculty_assignments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    wave_id = Column(String, ForeignKey("draft_waves.id"), nullable=False)
    faculty_id = Column(String, ForeignKey("faculty.id"), nullable=False)
    notified_at = Column(DateTime, nullable=True)  # When initial email was sent
    reminder_sent_at = Column(DateTime, nullable=True)  # When reminder email was sent (48hr)

    created_at = Column(DateTime, default=datetime.utcnow)

    wave = relationship("DraftWave", back_populates="faculty_assignments")
    faculty = relationship("Faculty")

    __table_args__ = (
        Index('idx_wave_faculty_unique', 'wave_id', 'faculty_id', unique=True),
    )


class WeekDraftStatus(Base):
    """Tracks capacity status for each week in the draft"""
    __tablename__ = "week_draft_status"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    config_id = Column(String, ForeignKey("draft_wave_configs.id"), nullable=False)
    week_id = Column(String, ForeignKey("service_weeks.id"), nullable=False)

    unavailable_count = Column(Integer, default=0)  # Count of unavailable requests
    volunteer_count = Column(Integer, default=0)  # Count of volunteer requests

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    config = relationship("DraftWaveConfig", back_populates="week_status")
    week = relationship("ServiceWeek")

    __table_args__ = (
        Index('idx_week_status_config_week', 'config_id', 'week_id', unique=True),
    )


class DraftWeekRequest(Base):
    """Individual faculty requests for unavailability or volunteering"""
    __tablename__ = "draft_week_requests"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    config_id = Column(String, ForeignKey("draft_wave_configs.id"), nullable=False)
    faculty_id = Column(String, ForeignKey("faculty.id"), nullable=False)
    week_id = Column(String, ForeignKey("service_weeks.id"), nullable=False)

    request_type = Column(String, nullable=False)  # 'unavailable' or 'volunteer'
    submitted_at = Column(DateTime, default=datetime.utcnow)

    config = relationship("DraftWaveConfig", back_populates="requests")
    faculty = relationship("Faculty")
    week = relationship("ServiceWeek")

    __table_args__ = (
        Index('idx_draft_request_faculty_week', 'faculty_id', 'week_id'),
        Index('idx_draft_request_config', 'config_id'),
    )


# ==========================================
# INSTANCE CONFIGURATION
# ==========================================

class InstanceConfig(Base):
    """
    Key-value store for all group-specific configuration.
    Each key holds a JSON-encoded value.  The setup wizard writes here;
    the rest of the app reads here instead of hardcoded constants.

    Well-known keys (all values are JSON):
      group_name          str   — display name for this deployment
      org_name            str   — parent organisation
      app_name            str   — shown in browser tab / wordmark
      setup_complete      bool  — false until the wizard finishes
      scheduling_model    str   — "weekly_blocks" | "shift_based"
      shift_config        obj   — { shifts: [{key, label, start, end, slots_needed}] }
      service_types       list  — [{key, label, slots_needed, point_cost}]
      faculty_attributes  list  — [{key, label, type, options?, required?}]
      scheduling_rules    obj   — {weeks_per_year, academic_year_start_month, ...}
      features            obj   — {moonlighting, draft_system, service_availability, ...}
      branding            obj   — {org_label, accent_color}
    """
    __tablename__ = "instance_config"

    key        = Column(String, primary_key=True)
    value      = Column(Text, nullable=False, default='null')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ==========================================
# SHIFT-BASED SCHEDULING  (APP / ICU model)
# ==========================================

class SchedulePeriod(Base):
    """
    One atomic scheduling slot — a single shift on a single date.
    Generated by the period generator from the instance shift_config.
    """
    __tablename__ = "schedule_periods"

    id            = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    rotation_key  = Column(String, nullable=False, index=True)   # e.g. "micu"
    period_date   = Column(Date, nullable=False, index=True)
    shift_type    = Column(String, nullable=False)                # "day" | "night" | custom
    start_time    = Column(String, nullable=False)                # "07:00"
    end_time      = Column(String, nullable=False)                # "19:00"
    slots_needed  = Column(Integer, nullable=False, default=2)   # target staffing
    min_slots     = Column(Integer, nullable=False, default=1)   # below this = understaffed
    max_slots     = Column(Integer, nullable=False, default=3)   # above target only manually
    is_holiday    = Column(Boolean, default=False)
    note          = Column(Text, nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)

    assignments = relationship("PeriodAssignment", back_populates="period",
                               cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('rotation_key', 'period_date', 'shift_type',
                         name='uq_period_rotation_date_shift'),
        Index('ix_schedule_periods_date_rotation', 'period_date', 'rotation_key'),
    )


class PeriodAssignment(Base):
    """
    Links a provider to a specific shift period.
    This is the actual schedule — one row per provider per shift.
    """
    __tablename__ = "period_assignments"

    id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    period_id   = Column(String, ForeignKey("schedule_periods.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    provider_id = Column(String, ForeignKey("faculty.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    status      = Column(String, nullable=False, default="assigned")  # assigned|tentative|blocked
    role        = Column(String, nullable=False, default="provider")  # provider|student — students don't count toward staffing
    is_manual   = Column(Boolean, default=True)
    assigned_by = Column(String, ForeignKey("faculty.id"), nullable=True)
    note        = Column(Text, nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    period   = relationship("SchedulePeriod", back_populates="assignments")
    provider = relationship("Faculty", foreign_keys=[provider_id])
    assigner = relationship("Faculty", foreign_keys=[assigned_by])

    __table_args__ = (
        UniqueConstraint('period_id', 'provider_id', name='uq_period_provider'),
        Index('ix_period_assignments_provider', 'provider_id'),
    )


# ==========================================
# PROVIDER CONSTRAINTS
# ==========================================

class ProviderConstraint(Base):
    """
    Extensible constraint store for scheduling rules per provider.
    All constraint data lives in constraint_value as JSON so new constraint
    types can be added without schema changes.

    Known constraint_type values:
      max_consecutive_shifts   {"max": 6}
      shift_restriction        {"allowed": ["day"]}  or ["night"] or ["day","night"]
      max_shifts_per_week      {"max": 4}
      unavailable_period       {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
      prefer_not               {"shift_type": "night", "reason": "childcare"}
    """
    __tablename__ = "provider_constraints"

    id               = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    faculty_id       = Column(String, ForeignKey("faculty.id", ondelete="CASCADE"),
                              nullable=False, index=True)
    constraint_type  = Column(String, nullable=False)
    constraint_value = Column(Text, nullable=False, default='{}')
    priority         = Column(Integer, nullable=False, default=50)  # 1=hard … 100=soft
    is_active        = Column(Boolean, nullable=False, default=True)
    created_by       = Column(String, ForeignKey("faculty.id"), nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)

    faculty  = relationship("Faculty", foreign_keys=[faculty_id])
    creator  = relationship("Faculty", foreign_keys=[created_by])

    __table_args__ = (
        Index('ix_provider_constraints_faculty', 'faculty_id', 'is_active'),
    )


# ==========================================
# DATABASE INITIALIZATION
# ==========================================

def init_db():
    """Initialize database with tables and optimizations"""
    print("[Database] Creating tables and indexes...")
    Base.metadata.create_all(bind=engine)
    
    try:
        with engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA cache_size=-20000"))
            conn.execute(text("PRAGMA mmap_size=10485760"))
            conn.execute(text("PRAGMA synchronous=NORMAL"))
            
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_faculty_email ON faculty(email)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_faculty_active ON faculty(active)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_unavailability_requests_faculty_week 
                ON unavailability_requests(faculty_id, week_id)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_unavailability_requests_status 
                ON unavailability_requests(status)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_service_weeks_number 
                ON service_weeks(week_number)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_service_weeks_year 
                ON service_weeks(year)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_service_assignments_faculty_week 
                ON service_week_assignments(faculty_id, week_id)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_service_assignments_service_type 
                ON service_week_assignments(service_type)
            """))
            
            conn.execute(text("ANALYZE"))
            conn.commit()
        print("[Database] Initialization complete with optimizations")
    except Exception as e:
        print(f"[Database] Warning: Could not apply optimizations: {e}")
        print("[Database] Initialization complete (without optimizations)")


def seed_message_boards(db: Session):
    """Seed default message boards if they don't exist"""
    boards = [
        MessageBoard(
            id="general",
            name="General Discussion",
            description="Announcements, questions, and discussions for all faculty",
            icon="💬",
            requires_moonlighting=False,
            display_order=1
        ),
        MessageBoard(
            id="moonlighting",
            name="Moonlighting",
            description="IRPA shifts, night coverage, and moonlighting-related discussions",
            icon="🌙",
            requires_moonlighting=True,
            display_order=2
        )
    ]
    
    for board in boards:
        existing = db.query(MessageBoard).filter_by(id=board.id).first()
        if not existing:
            db.add(board)
    
    db.commit()


def get_db():
    """Dependency for FastAPI endpoints"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
