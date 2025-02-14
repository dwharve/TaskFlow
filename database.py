from contextlib import contextmanager
from models import db

@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = db.session()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close() 