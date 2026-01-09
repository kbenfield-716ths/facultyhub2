# backend/models.py
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Boolean, Date, DateTime,
    ForeignKey, create_engine, text, Text, Index
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session
import os
import uuid

# Use persistent volume if available, fallback to local
db_path = "/data/moonlighter.db" if os.path.exists("/data") else "./moonlighter.db"
DATABASE_URL = f"sqlite:///{db_path}"

Base = declarative_base()
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

#===========================================
# SECURITY UPGRADE
#===========================================
# Add to backend/models.py

from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Integer, Index

class AuditLog(Base):
    """Audit log for tracking admin actions"""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    user_id = Column(String, nullable=False, index=True)  # Faculty ID who performed action
    user_name = Column(String, nullable=False)
    action = Column(String, nullable=False, index=True)  # e.g., "DELETE_PROVIDER", "CLEAR_MONTH"
    resource_type = Column(String, nullable=True, index=True)  # e.g., "Provider", "Month"
    resource_id = Column(String, nullable=True)
    details = Column(Text, nullable=True)  # JSON string with before/after state
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


# Add to Faculty model (modifications)
class Faculty(Base):
    __tablename__ = "faculty"
    
    # ... existing fields ...
    
    # Add these new fields (with defaults for backward compatibility)
    password_reset_required = Column(Boolean, default=False)
    password_last_changed = Column(DateTime, nullable=True)
    failed_login_attempts = Column(Integer, default=0)
    account_locked_until = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    last_login_ip = Column(String, nullable=True)

# ==========================================
# KNOWLEDGE BASE
# ==========================================

class KnowledgeBaseArticle(Base):
    __tablename__ = "knowledge_base_articles"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    description = Column(String, nullable=False)  # Short summary
    content = Column(Text, nullable=False)  # Full Markdown content
    category = Column(String, nullable=False)  # Policies, Procedures, Clinical Guidelines, IT Support
    
    # Publishing
    is_published = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)
    
    # Metadata
    created_by = Column(String, ForeignKey("faculty.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    author = relationship("Faculty", foreign_keys=[created_by])

# ==========================================
# DRAFT SYSTEM BASE
# ==========================================


class DraftRound(Base):
    __tablename__ = "draft_rounds"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    year = Column(Integer, nullable=False)
    round_number = Column(Integer, default=1)
    status = Column(String, default='pending')  # 'pending', 'active', 'paused', 'completed'
    window_size = Column(Integer, default=5)  # How many faculty can select at once
    hours_per_slot = Column(Integer, default=72)  # Hours each faculty has to submit
    
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    slots = relationship("DraftSlot", back_populates="draft_round", cascade="all, delete-orphan")


class DraftSlot(Base):
    __tablename__ = "draft_slots"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    round_id = Column(String, ForeignKey("draft_rounds.id"), nullable=False)
    faculty_id = Column(String, ForeignKey("faculty.id"), nullable=False)
    priority_order = Column(Integer, nullable=False)  # 1, 2, 3, etc.
    
    status = Column(String, default='waiting')  # 'waiting', 'active', 'submitted', 'expired', 'skipped'
    notified_at = Column(DateTime, nullable=True)
    deadline = Column(DateTime, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    draft_round = relationship("DraftRound", back_populates="slots")
    faculty = relationship("Faculty")

# ==========================================
# MOONLIGHTING MODELS (Existing)
# ==========================================

class Provider(Base):
    """Faculty member for moonlighting shifts"""
    __tablename__ = "providers"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    email = Column(String, nullable=True)
    
    signups = relationship("Signup", back_populates="provider")
    assignments = relationship("Assignment", back_populates="provider")


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
    provider_id = Column(String, ForeignKey("providers.id"), nullable=False, index=True)
    shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=False, index=True)
    desired_nights = Column(Integer, nullable=False)
    locked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    provider = relationship("Provider", back_populates="signups")
    shift = relationship("Shift", back_populates="signups")


class Assignment(Base):
    """Final moonlighting shift assignments"""
    __tablename__ = "assignments"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    provider_id = Column(String, ForeignKey("providers.id"), nullable=False)
    shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    provider = relationship("Provider", back_populates="assignments")
    shift = relationship("Shift", back_populates="assignments")


# ==========================================
# FACULTY SCHEDULING MODELS (Service Availability)
# ==========================================

class Faculty(Base):
    """Faculty member with scheduling profile and authentication"""
    __tablename__ = "faculty"
    
    # Core identity (UVA computing ID: "KE4Z", "IN2C", etc.)
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False)
    
    # Authentication
    password_hash = Column(String)
    password_changed = Column(Boolean, default=False)
    registered = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    
    # Scheduling profile
    rank = Column(String, nullable=False)  # assistant, associate, full
    clinical_effort_pct = Column(Integer, nullable=False)
    base_points = Column(Integer, nullable=False)
    bonus_points = Column(Integer, default=0)  # Earned from volunteering
    active = Column(Boolean, default=True)
    
    # Moonlighting participation (single source of truth)
    moonlighter = Column(Boolean, default=False, nullable=False)  # Whether faculty does moonlighting shifts
    
    # Service week commitments (for inpatient scheduling)
    # These define how many weeks per year this faculty member is expected to work each service
    micu_weeks = Column(Integer, default=0)        # Number of MICU weeks per year
    app_icu_weeks = Column(Integer, default=0)     # Number of APP-ICU weeks per year  
    procedure_weeks = Column(Integer, default=0)   # Number of Procedure weeks per year
    consult_weeks = Column(Integer, default=0)     # Number of Consult weeks per year
    
    # Relationships
    unavailability_requests = relationship("UnavailabilityRequest", back_populates="faculty")
    service_assignments = relationship("ServiceWeekAssignment", back_populates="faculty")
    
    # Property for compatibility with message board access control
    # This ensures moonlighter and does_moonlighting are always synchronized
    @property
    def does_moonlighting(self):
        """Alias for moonlighter field - used by message board access control"""
        return self.moonlighter
    
    @does_moonlighting.setter
    def does_moonlighting(self, value):
        """Setter to keep fields synchronized"""
        self.moonlighter = value


class ServiceWeek(Base):
    """The 52 weeks of the academic year for service availability scheduling"""
    __tablename__ = "service_weeks"
    
    id = Column(String, primary_key=True, index=True)  # "W01-2026", "W02-2026", etc.
    week_number = Column(Integer, nullable=False)
    label = Column(String, nullable=False)  # "Week 1 (Jul 7)"
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    year = Column(Integer, nullable=False)
    
    # Week characteristics
    week_type = Column(String, default="regular")  # regular, summer, spring_break, thanksgiving, christmas
    point_cost_off = Column(Integer, default=5)     # Cost to request unavailability
    point_reward_work = Column(Integer, default=0)  # Bonus for volunteering
    min_staff_required = Column(Integer, default=5)
    
    # Historic data seeding (for previous years before system was deployed)
    historic_unavailable_count = Column(Integer, default=0)  # Number of faculty unavailable (from seed data)
    
    # Relationships
    unavailability_requests = relationship("UnavailabilityRequest", back_populates="week")
    service_assignments = relationship("ServiceWeekAssignment", back_populates="week")


class UnavailabilityRequest(Base):
    """Faculty unavailability requests for specific weeks"""
    __tablename__ = "unavailability_requests"
    
    id = Column(String, primary_key=True, index=True)
    faculty_id = Column(String, ForeignKey('faculty.id'), nullable=False, index=True)
    week_id = Column(String, ForeignKey('service_weeks.id'), nullable=False, index=True)
    
    # Status: "unavailable" (requests time off), "available" (volunteers), "assigned" (final)
    status = Column(String, nullable=False, default="unavailable")
    
    # Points tracking
    points_spent = Column(Integer, default=0)   # For requesting unavailability
    points_earned = Column(Integer, default=0)  # For volunteering
    
    # Draft priority tracking
    gives_priority = Column(Boolean, default=False)  # Working holiday gives next year priority
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    faculty = relationship("Faculty", back_populates="unavailability_requests")
    week = relationship("ServiceWeek", back_populates="unavailability_requests")


class ServiceWeekAssignment(Base):
    """Actual service week assignments (MICU, APP-ICU, Procedures, Consults)"""
    __tablename__ = "service_week_assignments"
    
    id = Column(String, primary_key=True, index=True)
    faculty_id = Column(String, ForeignKey('faculty.id'), nullable=False, index=True)
    week_id = Column(String, ForeignKey('service_weeks.id'), nullable=False, index=True)
    
    # Service type: "MICU", "APP-ICU", "Procedures", "Consults"
    service_type = Column(String, nullable=False, index=True)
    
    # Import tracking
    imported = Column(Boolean, default=False)  # True if from historic CSV
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    faculty = relationship("Faculty", back_populates="service_assignments")
    week = relationship("ServiceWeek", back_populates="service_assignments")

# ==========================================
# Message Boards
# ==========================================

class MessageBoard(Base):
    """Message boards (General, Moonlighting, etc.)"""
    __tablename__ = "message_boards"
    
    id = Column(String, primary_key=True)  # 'general', 'moonlighting'
    name = Column(String(100), nullable=False)
    description = Column(Text)
    icon = Column(String(10))  # Emoji
    requires_moonlighting = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
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
    
    subject = Column(Text)  # Only for top-level threads
    content = Column(Text, nullable=False)
    is_pinned = Column(Boolean, default=False)
    is_edited = Column(Boolean, default=False)
    edited_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    board = relationship("MessageBoard", back_populates="messages")
    author = relationship("Faculty", foreign_keys=[author_id])
    parent = relationship("Message", remote_side=[id], backref="replies")
    reactions = relationship("MessageReaction", back_populates="message", cascade="all, delete-orphan")
    read_status = relationship("MessageReadStatus", back_populates="message", cascade="all, delete-orphan")
    
    # Indexes
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
    reaction = Column(String(10), nullable=False)  # Emoji
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    message = relationship("Message", back_populates="reactions")
    faculty = relationship("Faculty")
    
    # Unique constraint: one reaction type per faculty per message
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
    
    # Relationships
    message = relationship("Message", back_populates="read_status")
    faculty = relationship("Faculty")
    
    # Unique constraint: one read status per faculty per message
    __table_args__ = (
        Index('idx_read_status_faculty', 'faculty_id'),
        Index('idx_read_status_message', 'message_id'),
        Index('idx_read_status_unique', 'message_id', 'faculty_id', unique=True),
    )
    
    def __repr__(self):
        return f"<MessageReadStatus(message={self.message_id}, faculty={self.faculty_id})>"
        
# ==========================================
# DATABASE INITIALIZATION
# ==========================================

def init_db():
    """Initialize database with tables and optimizations"""
    print("[Database] Creating tables and indexes...")
    Base.metadata.create_all(bind=engine)
    
    # Database optimizations using text() for raw SQL
    try:
        with engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA cache_size=-20000"))
            conn.execute(text("PRAGMA mmap_size=10485760"))
            conn.execute(text("PRAGMA synchronous=NORMAL"))
            
            # Add indexes for faculty scheduling tables
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
