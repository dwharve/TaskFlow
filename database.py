from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
import os

# Create engine
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///instance/database.db')

# Configure engine based on database type
if DATABASE_URL.startswith('sqlite'):
    # SQLite specific configuration
    engine = create_engine(
        DATABASE_URL,
        connect_args={'check_same_thread': False}  # Required for SQLite
    )
else:
    # PostgreSQL configuration
    engine = create_engine(
        DATABASE_URL,
        poolclass=QueuePool,
        pool_size=20,
        max_overflow=10,
        pool_timeout=30,
        pool_pre_ping=True
    )

# Create session factory
Session = scoped_session(sessionmaker(bind=engine))

def get_session():
    """Get the current session"""
    return Session

@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = Session()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()

def init_db():
    """Initialize the database"""
    from models import Base, Settings
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    # Initialize with session scope to ensure proper transaction handling
    with session_scope() as session:
        # Create default settings if they don't exist
        if not session.query(Settings).filter_by(key='SECRET_KEY').first():
            import secrets
            setting = Settings(key='SECRET_KEY', value=secrets.token_hex(32))
            session.add(setting)
            session.commit() 