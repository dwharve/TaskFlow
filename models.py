from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import json
from sqlalchemy import event
from sqlalchemy.orm import scoped_session
from contextlib import contextmanager

# Initialize SQLAlchemy with thread-safe session
db = SQLAlchemy()

# Models
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    tasks = db.relationship('Task', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def update_last_login(self):
        from database import session_scope
        with session_scope() as session:
            self.last_login = datetime.utcnow()
            session.merge(self)
    
    def to_dict(self):
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
        from database import session_scope
        with session_scope() as session:
            return session.query(User).all()
    
    @staticmethod
    def get_active_users():
        from database import session_scope
        with session_scope() as session:
            return session.query(User).filter_by(is_active=True).all()
    
    def deactivate(self):
        from database import session_scope
        with session_scope() as session:
            user = session.merge(self)
            user.is_active = False
    
    def activate(self):
        from database import session_scope
        with session_scope() as session:
            user = session.merge(self)
            user.is_active = True

class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    input_block = db.Column(db.String(100), nullable=False)
    block_chain = db.Column(db.Text, nullable=False, default='[]')
    target_url = db.Column(db.String(500), nullable=False)
    schedule = db.Column(db.String(100))
    parameters = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')
    last_run = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    block_data = db.Column(db.Text)
    version = db.Column(db.Integer, default=1)  # For optimistic locking
    
    item_states = db.relationship('ItemState', backref='task', lazy=True,
                                cascade='all, delete-orphan')
    
    def update_status(self, new_status):
        """Thread-safe status update with optimistic locking"""
        from database import session_scope
        with session_scope() as session:
            task = session.merge(self)
            current_version = task.version
            task.status = new_status
            task.version += 1
            session.flush()
            
            # Verify no other transaction has modified this record
            if task.version != current_version + 1:
                session.rollback()
                raise Exception("Task was modified by another transaction")
    
    def set_parameters(self, parameters):
        """Set parameters for all blocks in the chain"""
        if isinstance(parameters, dict):
            parameters = json.dumps(parameters)
        self.parameters = parameters
    
    def get_parameters(self):
        """Get parameters for all blocks"""
        return json.loads(self.parameters) if self.parameters else {}
    
    def set_block_chain(self, blocks):
        """Set the chain of blocks to execute"""
        if isinstance(blocks, list):
            blocks = json.dumps(blocks)
        self.block_chain = blocks
    
    def get_block_chain(self):
        """Get the chain of blocks"""
        return json.loads(self.block_chain) if self.block_chain else []
    
    def set_block_data(self, data):
        """Set data for all blocks in the chain"""
        if isinstance(data, dict):
            data = json.dumps(data)
        self.block_data = data
    
    def get_block_data(self):
        """Get data for all blocks"""
        default_data = {
            "input": [],
            "processing": {},
            "action": {}
        }
        
        if not self.block_data:
            return default_data
            
        try:
            data = json.loads(self.block_data)
            return {
                "input": data.get("input", []),
                "processing": data.get("processing", {}),
                "action": data.get("action", {})
            }
        except (json.JSONDecodeError, TypeError):
            return default_data

class ItemState(db.Model):
    """Model for storing seen items for the item monitor plugin"""
    __tablename__ = 'item_states'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False)
    item_hash = db.Column(db.String(64), nullable=False)  # SHA-256 hash is 64 chars
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Create indexes
    __table_args__ = (
        db.Index('idx_task_hash', 'task_id', 'item_hash', unique=True),  # For fast lookups and uniqueness
        db.Index('idx_task_created', 'task_id', 'created_at'),  # For cleanup
    )

    def __repr__(self):
        return f'<ItemState {self.task_id}:{self.item_hash}>'

class Settings(db.Model):
    __tablename__ = 'settings'
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    version = db.Column(db.Integer, default=1)  # For optimistic locking

    @staticmethod
    def get_setting(key, default=None):
        from database import session_scope
        with session_scope() as session:
            setting = session.query(Settings).get(key)
            return setting.value if setting else default

    @staticmethod
    def set_setting(key, value):
        from database import session_scope
        with session_scope() as session:
            setting = session.query(Settings).get(key)
            if setting:
                current_version = setting.version
                setting.value = value
                setting.version += 1
                session.flush()
                
                # Verify no other transaction has modified this record
                if setting.version != current_version + 1:
                    session.rollback()
                    raise Exception("Setting was modified by another transaction")
            else:
                setting = Settings(key=key, value=value)
                session.add(setting)
            return setting

# Removed plugin registration code

# ... existing code ... 