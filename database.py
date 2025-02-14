from contextlib import contextmanager
from models import db
import threading
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy import event

# Thread local storage for database sessions
thread_local = threading.local()

def get_session():
    """Get or create a scoped database session for the current thread"""
    if not hasattr(thread_local, 'session'):
        # Create a new scoped session with SQLAlchemy 2.0 compatible settings
        session_factory = sessionmaker(
            bind=db.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False  # Prevent detached instance errors
        )
        thread_local.session = scoped_session(session_factory)
        
        # Set up session events for cleanup
        @event.listens_for(thread_local.session, 'after_commit')
        def after_commit(session):
            """Expire all instances after commit to ensure fresh data"""
            session.expire_all()
        
        @event.listens_for(thread_local.session, 'after_rollback')
        def after_rollback(session):
            """Expire all instances after rollback"""
            session.expire_all()
    
    return thread_local.session

@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = get_session()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        # Just expire the objects but don't remove the session
        # This allows the session to be reused within the same request
        session.expire_all() 