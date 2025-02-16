from contextlib import contextmanager
from models import db
import threading
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy import event

# Thread local storage for database sessions
thread_local = threading.local()

# Create session factory but don't configure it yet
Session = scoped_session(sessionmaker())

def init_db(app):
    """Initialize the database with the Flask app context
    
    Args:
        app: Flask application instance
    """
    with app.app_context():
        # Configure session to use Flask-SQLAlchemy's engine
        Session.configure(bind=db.engine)
        
        # Create all tables
        db.create_all()
        
        # Commit any pending transactions
        db.session.commit()

def get_session():
    """Get the current database session"""
    return Session

@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations
    
    Yields:
        Session: Database session
    """
    session = Session()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close() 