# backend/models.py
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Boolean, Date, DateTime, Float,
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
    
    # Scheduling profile
    rank = Column(String, nullable=False)
    clinical_effort_pct = Column(Integer, nullable=False)
    base_points = Column(Integer, nullable=False)
    bonus_points = Column(Integer, default=0)
    active = Column(Boolean, default=True)
    
    # Moonlighting participation
    moonlighter = Column(Boolean, default=False, nullable=False)
    draft_exempt = Column(Boolean, default=False, nullable=False)  # Exclude from draft priority system

    # Service week commitments
    micu_weeks = Column(Integer, default=0)
    app_icu_weeks = Column(Integer, default=0)
    procedure_weeks = Column(Integer, default=0)
    consult_weeks = Column(Integer, default=0)
    
    # Relationships
    unavailability_requests = relationship("UnavailabilityRequest", back_populates="faculty")
    service_assignments = relationship("ServiceWeekAssignment", back_populates="faculty", foreign_keys="ServiceWeekAssignment.faculty_id")
    moonlighting_signups = relationship("Signup", foreign_keys="Signup.provider_id")
    moonlighting_assignments = relationship("Assignment", foreign_keys="Assignment.provider_id")
    
    @property
    def does_moonlighting(self):
        """Alias for moonlighter field - used by message board access control"""
        return self.moonlighter
    
    @does_moonlighting.setter
    def does_moonlighting(self, value):
        """Setter to keep fields synchronized"""
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
