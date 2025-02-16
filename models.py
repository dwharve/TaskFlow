from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import json
from sqlalchemy import event
from sqlalchemy.orm import scoped_session
from contextlib import contextmanager
import logging
import time
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
import bcrypt

# Create base model class
Base = declarative_base()

# Initialize Flask-SQLAlchemy
db = SQLAlchemy()

# Configure logger
logger = logging.getLogger(__name__)

# Models
class User(Base, db.Model):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    
    # Relationships
    tasks = relationship('Task', backref='user', lazy=True)
    
    def set_password(self, password):
        """Hash and set the password"""
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    def check_password(self, password):
        """Check if the password matches"""
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
    
    def update_last_login(self):
        from database import session_scope
        with session_scope() as session:
            self.last_login = datetime.utcnow()
            session.merge(self)
    
    @property
    def is_authenticated(self):
        return True
    
    @property
    def is_anonymous(self):
        return False
    
    def get_id(self):
        return str(self.id)
    
    def to_dict(self):
        """Convert user to dictionary for API responses"""
        return {
            'id': self.id,
            'username': self.username,
            'is_admin': self.is_admin,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }
    
    @staticmethod
    def get_all_users():
        """Get all users"""
        return User.query.all()
    
    @staticmethod
    def get_active_users():
        from database import session_scope
        with session_scope() as session:
            return session.query(User).filter_by(is_active=True).all()
    
    def deactivate(self):
        """Deactivate the user"""
        self.is_active = False
        db.session.commit()
    
    def activate(self):
        """Activate the user"""
        self.is_active = True
        db.session.commit()

class Task(Base, db.Model):
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    schedule = Column(String(100))
    status = Column(String(20), default='pending')
    last_run = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    version = Column(Integer, default=1)  # For optimistic locking
    
    # Relationships
    blocks = relationship('Block', backref='task', lazy=True, cascade='all, delete-orphan')
    item_states = relationship('ItemState', backref='task', lazy=True, cascade='all, delete-orphan')
    
    def update_status(self, new_status, max_retries=3):
        """Thread-safe status update with optimistic locking and retries"""
        from database import session_scope
        last_error = None
        
        for attempt in range(max_retries):
            try:
                with session_scope() as session:
                    # Get fresh instance
                    task = session.query(Task).get(self.id)
                    if not task:
                        raise ValueError(f"Task {self.id} not found")
                    
                    # Update status and version
                    task.status = new_status
                    task.version += 1
                    
                    if new_status in ['completed', 'failed']:
                        task.last_run = datetime.utcnow()
                    
                    return True
            except Exception as e:
                last_error = e
                continue
        
        # If we get here, we've exhausted our retries
        raise last_error if last_error else Exception("Failed to update task status")
    
    def get_block_chain(self):
        """Get the execution chain of blocks"""
        blocks_by_id = {block.id: block for block in self.blocks}
        connections = []
        
        for block in self.blocks:
            for conn in block.inputs:
                connections.append({
                    'from': blocks_by_id[conn.source_block_id].name,
                    'to': blocks_by_id[conn.target_block_id].name,
                    'input': conn.input_name
                })
        
        return {
            'blocks': [{'id': b.id, 'name': b.name, 'type': b.type} for b in self.blocks],
            'connections': connections
        }
    
    def get_block_data(self):
        """Get the latest data for each block"""
        return {
            block.name: json.loads(block.last_result) if block.last_result else None
            for block in self.blocks
        }
    
    def set_block_data(self, data):
        """Set block data from execution results
        
        Args:
            data: Dictionary mapping block names to their results
        """
        blocks_by_name = {block.name: block for block in self.blocks}
        
        for block_name, result in data.items():
            if block_name in blocks_by_name:
                blocks_by_name[block_name].last_result = json.dumps(result)

class Block(Base, db.Model):
    __tablename__ = 'blocks'
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey('tasks.id'), nullable=False)
    name = Column(String(100), nullable=False)
    type = Column(String(20), nullable=False)  # input, processing, or action
    parameters = Column(JSON)
    position_x = Column(Integer)
    position_y = Column(Integer)
    last_result = Column(Text)
    display_name = Column(String(100))
    
    # Relationships
    inputs = relationship('BlockConnection', 
                         foreign_keys='BlockConnection.target_block_id',
                         backref='target_block',
                         lazy=True,
                         cascade='all, delete-orphan')
    outputs = relationship('BlockConnection',
                          foreign_keys='BlockConnection.source_block_id',
                          backref='source_block',
                          lazy=True,
                          cascade='all, delete-orphan')
    
    def get_parameters(self):
        """Get block parameters"""
        return self.parameters or {}
    
    def set_parameters(self, params):
        """Set block parameters
        
        Args:
            params: Dictionary of parameter values
        """
        self.parameters = params

class BlockConnection(Base, db.Model):
    __tablename__ = 'block_connections'
    id = Column(Integer, primary_key=True)
    source_block_id = Column(Integer, ForeignKey('blocks.id'), nullable=False)
    target_block_id = Column(Integer, ForeignKey('blocks.id'), nullable=False)
    input_name = Column(String(100), nullable=False)

class ItemState(Base, db.Model):
    __tablename__ = 'item_states'
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey('tasks.id'), nullable=False)
    item_id = Column(String(255), nullable=False)
    state = Column(String(20), nullable=False)  # new, processed
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('task_id', 'item_id', name='_task_item_uc'),
    )

class Settings(Base, db.Model):
    __tablename__ = 'settings'
    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text)
    
    @staticmethod
    def get_setting(key, session=None):
        """Get a setting value
        
        Args:
            key: Setting key
            session: Optional database session
        
        Returns:
            Setting value or None if not found
        """
        if session:
            setting = session.query(Settings).filter_by(key=key).first()
        else:
            setting = Settings.query.filter_by(key=key).first()
        return setting.value if setting else None
    
    @staticmethod
    def set_setting(key, value, session=None):
        """Set a setting value
        
        Args:
            key: Setting key
            value: Setting value
            session: Optional database session
        """
        if session:
            setting = session.query(Settings).filter_by(key=key).first()
        else:
            setting = Settings.query.filter_by(key=key).first()
            
        if setting:
            setting.value = value
        else:
            setting = Settings(key=key, value=value)
            if session:
                session.add(setting)
            else:
                db.session.add(setting)
                db.session.commit()

class TaskLock(db.Model):
    """Model for task execution locking"""
    __tablename__ = 'task_locks'
    
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), primary_key=True)
    worker_id = db.Column(db.String(100), nullable=False)
    locked_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    
    @staticmethod
    def acquire_lock(task_id, worker_id, lock_duration=60):
        """Attempt to acquire a lock for a task
        
        Args:
            task_id: ID of task to lock
            worker_id: ID of worker attempting to acquire lock
            lock_duration: Lock duration in seconds
            
        Returns:
            True if lock acquired, False otherwise
        """
        from database import session_scope
        
        with session_scope() as session:
            try:
                # First cleanup expired locks
                session.query(TaskLock).filter(
                    TaskLock.expires_at < datetime.utcnow()
                ).delete()
                
                # Try to get existing lock
                lock = session.query(TaskLock).filter(
                    TaskLock.task_id == task_id
                ).first()
                
                if lock:
                    # Lock exists and hasn't expired
                    return False
                
                # Create new lock
                lock = TaskLock(
                    task_id=task_id,
                    worker_id=worker_id,
                    expires_at=datetime.utcnow() + timedelta(seconds=lock_duration)
                )
                session.add(lock)
                session.commit()
                return True
                
            except Exception as e:
                logger.error(f"Error acquiring lock for task {task_id}: {str(e)}")
                session.rollback()
                return False
    
    @staticmethod
    def release_lock(task_id, worker_id):
        """Release a task lock
        
        Args:
            task_id: ID of task to unlock
            worker_id: ID of worker that held the lock
        """
        from database import session_scope
        
        with session_scope() as session:
            try:
                # Only delete if this worker owns the lock
                session.query(TaskLock).filter(
                    TaskLock.task_id == task_id,
                    TaskLock.worker_id == worker_id
                ).delete()
                session.commit()
            except Exception as e:
                logger.error(f"Error releasing lock for task {task_id}: {str(e)}")
                session.rollback()

# Removed plugin registration code

# ... existing code ... 