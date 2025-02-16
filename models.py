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

# Initialize SQLAlchemy with thread-safe session
db = SQLAlchemy()

# Configure logger
logger = logging.getLogger(__name__)

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
    schedule = db.Column(db.String(100))
    status = db.Column(db.String(20), default='pending')
    last_run = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    version = db.Column(db.Integer, default=1)  # For optimistic locking
    
    # Relationships
    blocks = db.relationship('Block', backref='task', lazy=True, cascade='all, delete-orphan')
    item_states = db.relationship('ItemState', backref='task', lazy=True, cascade='all, delete-orphan')
    
    def update_status(self, new_status, max_retries=3):
        """Thread-safe status update with optimistic locking and retries"""
        from database import session_scope
        last_error = None
        
        for attempt in range(max_retries):
            try:
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
                    
                    # If we got here, the update was successful
                    logger.info(f"Successfully updated task {task.id} status to {new_status} (attempt {attempt + 1})")
                    return True
                    
            except Exception as e:
                last_error = e
                logger.warning(f"Failed to update task {self.id} status on attempt {attempt + 1}: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(0.1 * (attempt + 1))  # Exponential backoff
                continue
        
        # If we got here, all retries failed
        logger.error(f"Failed to update task {self.id} status after {max_retries} attempts")
        raise last_error
    
    def get_block_data(self):
        """Get data for all blocks"""
        block_data = {
            "input": {},
            "processing": {},
            "action": {}
        }
        
        for block in self.blocks:
            if block.data:
                try:
                    data = json.loads(block.data)
                    block_data[block.type][block.name] = data
                except (json.JSONDecodeError, TypeError):
                    continue
        
        return block_data
    
    def set_block_data(self, results):
        """Store block execution results
        
        Args:
            results: Dictionary containing results for each block type
        """
        for block_type, type_results in results.items():
            for block_name, block_data in type_results.items():
                # Find the block
                block = next((b for b in self.blocks 
                            if b.type == block_type and b.name == block_name), None)
                if block:
                    block.set_data(block_data)

    def get_block_chain(self):
        """Get blocks in execution order (input -> processing -> action)
        
        Returns:
            List of blocks in execution order, with each block containing its connections
        """
        # Create a map of block_id -> block for easy lookup
        blocks_by_id = {block.id: block for block in self.blocks}
        
        # Create dependency graph
        dependencies = {}  # block_id -> set of block_ids it depends on
        for block in self.blocks:
            dependencies[block.id] = set()
            for conn in block.inputs:
                dependencies[block.id].add(conn.source_block_id)
        
        # Separate blocks by type
        input_blocks = []
        processing_blocks = []
        action_blocks = []
        
        for block in self.blocks:
            if block.type == 'input':
                input_blocks.append(block)
            elif block.type == 'processing':
                processing_blocks.append(block)
            elif block.type == 'action':
                action_blocks.append(block)
        
        # Build execution chain
        execution_chain = []
        
        # First add input blocks (they have no dependencies)
        execution_chain.extend(input_blocks)
        
        # Add processing blocks in dependency order
        while processing_blocks:
            # Find blocks whose dependencies are all satisfied
            ready_blocks = [
                block for block in processing_blocks
                if all(dep_id in {b.id for b in execution_chain} for dep_id in dependencies[block.id])
            ]
            
            if not ready_blocks and processing_blocks:
                # We have blocks but none are ready - must be a cycle
                break
            
            # Add ready blocks to chain
            for block in ready_blocks:
                execution_chain.append(block)
                processing_blocks.remove(block)
        
        # Finally add action blocks
        execution_chain.extend(action_blocks)
        
        # Add connection information to each block
        for block in execution_chain:
            block.input_connections = []
            block.output_connections = []
            
            # Add input connections
            for conn in block.inputs:
                if conn.source_block_id in blocks_by_id:
                    source_block = blocks_by_id[conn.source_block_id]
                    block.input_connections.append({
                        'source_block': source_block,
                        'input_name': conn.input_name
                    })
            
            # Add output connections
            for conn in block.outputs:
                if conn.target_block_id in blocks_by_id:
                    target_block = blocks_by_id[conn.target_block_id]
                    block.output_connections.append({
                        'target_block': target_block,
                        'input_name': conn.input_name
                    })
        
        return execution_chain

class Block(db.Model):
    """Model representing a block in a task"""
    __tablename__ = 'blocks'
    
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'input', 'processing', or 'action'
    display_name = db.Column(db.String(100))  # Display name for the block
    parameters = db.Column(db.Text)  # JSON string of parameters
    data = db.Column(db.Text)  # JSON string of block output data
    position_x = db.Column(db.Float)  # For UI positioning
    position_y = db.Column(db.Float)  # For UI positioning
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    outputs = db.relationship(
        'BlockConnection',
        foreign_keys='BlockConnection.source_block_id',
        backref='source_block',
        lazy=True,
        cascade='all, delete-orphan'
    )
    inputs = db.relationship(
        'BlockConnection',
        foreign_keys='BlockConnection.target_block_id',
        backref='target_block',
        lazy=True,
        cascade='all, delete-orphan'
    )
    
    def set_parameters(self, parameters):
        """Set block parameters"""
        if isinstance(parameters, dict):
            parameters = json.dumps(parameters)
        self.parameters = parameters
    
    def get_parameters(self):
        """Get block parameters"""
        return json.loads(self.parameters) if self.parameters else {}
    
    def set_data(self, data):
        """Set block output data"""
        if isinstance(data, (dict, list)):
            data = json.dumps(data)
        self.data = data
    
    def get_data(self):
        """Get block output data"""
        return json.loads(self.data) if self.data else None

class BlockConnection(db.Model):
    """Model representing a connection between blocks"""
    __tablename__ = 'block_connections'
    
    id = db.Column(db.Integer, primary_key=True)
    source_block_id = db.Column(db.Integer, db.ForeignKey('blocks.id', ondelete='CASCADE'), nullable=False)
    target_block_id = db.Column(db.Integer, db.ForeignKey('blocks.id', ondelete='CASCADE'), nullable=False)
    input_name = db.Column(db.String(50))  # Name of the input on the target block (for blocks with multiple inputs)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('source_block_id', 'target_block_id', 'input_name', name='unique_connection'),
    )

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
    def get_setting(key, default=None, session=None):
        """Get a setting value
        
        Args:
            key: Setting key
            default: Default value if setting doesn't exist
            session: Optional database session to use
            
        Returns:
            Setting value or default
        """
        if session is None:
            from database import session_scope
            with session_scope() as session:
                setting = session.query(Settings).get(key)
                return setting.value if setting else default
        else:
            setting = session.query(Settings).get(key)
            return setting.value if setting else default

    @staticmethod
    def set_setting(key, value, session=None):
        """Set a setting value
        
        Args:
            key: Setting key
            value: Setting value
            session: Optional database session to use
            
        Returns:
            Settings object
        """
        if session is None:
            from database import session_scope
            with session_scope() as session:
                return Settings._set_setting_with_session(key, value, session)
        else:
            return Settings._set_setting_with_session(key, value, session)
    
    @staticmethod
    def _set_setting_with_session(key, value, session):
        """Internal method to set setting with a session
        
        Args:
            key: Setting key
            value: Setting value
            session: Database session
            
        Returns:
            Settings object
        """
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