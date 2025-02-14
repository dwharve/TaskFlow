from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import json

# Initialize SQLAlchemy

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
        self.last_login = datetime.utcnow()
        db.session.commit()
    
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
        return User.query.all()
    
    @staticmethod
    def get_active_users():
        return User.query.filter_by(is_active=True).all()
    
    def deactivate(self):
        self.is_active = False
        db.session.commit()
    
    def activate(self):
        self.is_active = True
        db.session.commit()
    
    def __repr__(self):
        return f'<User {self.username}>'

class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    input_block = db.Column(db.String(100), nullable=False)  # The input (formerly scraping) block
    block_chain = db.Column(db.Text, nullable=False)  # JSON array of processing and action blocks in order
    target_url = db.Column(db.String(500), nullable=False)
    schedule = db.Column(db.String(100))
    parameters = db.Column(db.Text)  # JSON string of all block parameters
    status = db.Column(db.String(20), default='pending')
    last_run = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    block_data = db.Column(db.Text)  # JSON string containing data at each block stage
    
    # Add relationship to ItemState
    item_states = db.relationship('ItemState', backref='task', lazy=True,
                                cascade='all, delete-orphan')
    
    def set_parameters(self, parameters):
        """Set block parameters
        
        Args:
            parameters: Dictionary of parameters for all blocks in the chain
            Format: {
                "input": {...},
                "processing": {
                    "block_name": {...}
                },
                "action": {
                    "block_name": {...}
                }
            }
        """
        self.parameters = json.dumps(parameters)
    
    def get_parameters(self):
        """Get block parameters
        
        Returns:
            Dictionary of parameters for all blocks
        """
        return json.loads(self.parameters) if self.parameters else {}

    def set_block_chain(self, blocks):
        """Set the chain of blocks to execute
        
        Args:
            blocks: List of block identifiers in execution order
            Format: [
                {"type": "processing", "name": "block_name"},
                {"type": "action", "name": "block_name"}
            ]
        """
        self.block_chain = json.dumps(blocks)
    
    def get_block_chain(self):
        """Get the chain of blocks
        
        Returns:
            List of block identifiers in execution order
        """
        return json.loads(self.block_chain) if self.block_chain else []

    def set_block_data(self, data):
        """Set data for all blocks in the chain
        
        Args:
            data: Dictionary containing data at each stage
            Format: {
                "input": [...],
                "processing": {
                    "block_name": [...]
                },
                "action": {
                    "block_name": [...]
                }
            }
        """
        self.block_data = json.dumps(data)
    
    def get_block_data(self):
        """Get data for all blocks
        
        Returns:
            Dictionary containing data at each stage with default empty values
        """
        default_data = {
            "input": [],
            "processing": {},
            "action": {}
        }
        
        if not self.block_data:
            return default_data
            
        try:
            data = json.loads(self.block_data)
            # Ensure all required keys exist with defaults
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

    @staticmethod
    def get_setting(key, default=None):
        setting = Settings.query.get(key)
        return setting.value if setting else default

    @staticmethod
    def set_setting(key, value):
        setting = Settings.query.get(key)
        if setting:
            setting.value = value
        else:
            setting = Settings(key=key, value=value)
            db.session.add(setting)
        db.session.commit()
        return setting

# Removed plugin registration code

# ... existing code ... 