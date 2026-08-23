import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Text, event
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Use SQLite by default, but allow override via environment variable
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./monitor.db")

# SQLAlchemy setup
connect_args = {}
if "sqlite" in DATABASE_URL:
    connect_args = {"check_same_thread": False, "timeout": 15}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

# Enable Write-Ahead Logging (WAL) to allow simultaneous readers and writers in SQLite
if "sqlite" in DATABASE_URL:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class PipelineRun(Base):
    """Logs every execution of the pipeline monitor."""
    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    file_name = Column(String, default="N/A")
    storage_location = Column(String, default="landing/")
    status = Column(String) # e.g., 'SUCCESS', 'FAILURE'
    total_checks = Column(Integer, default=0)
    passed_checks = Column(Integer, default=0)
    failed_checks = Column(Integer, default=0)

    # One-to-many relationship with check results
    check_results = relationship("CheckResult", back_populates="run")

class CheckResult(Base):
    """Logs the result of an individual data quality check."""
    __tablename__ = "check_results"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("pipeline_runs.id"))
    check_name = Column(String) # e.g., 'schema_validation', 'null_check'
    status = Column(String) # 'PASS' or 'FAIL'
    details = Column(Text) # Additional context, like which columns failed
    timestamp = Column(DateTime, default=datetime.utcnow)

    run = relationship("PipelineRun", back_populates="check_results")

class Ticket(Base):
    """Incident tickets created when checks fail."""
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(Text)
    severity = Column(String) # 'LOW', 'MEDIUM', 'HIGH'
    status = Column(String, default="OPEN") # 'OPEN', 'IN_PROGRESS', 'RESOLVED'
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

def init_db():
    """Create all tables in the database and handle schema updates."""
    Base.metadata.create_all(bind=engine)
    
    # Auto-migration for SQLite to add missing columns without dropping tables
    if "sqlite" in DATABASE_URL:
        with engine.connect() as conn:
            for col, default_val in [("file_name", "N/A"), ("storage_location", "landing/")]:
                try:
                    conn.execute(f"ALTER TABLE pipeline_runs ADD COLUMN {col} VARCHAR DEFAULT '{default_val}'")
                except Exception:
                    pass # Column already exists

def get_session():
    """Yield a database session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

if __name__ == "__main__":
    init_db()
    print("Database tables initialized successfully.")
