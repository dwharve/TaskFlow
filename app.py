import os
import logging
import json
import asyncio
import secrets
import threading
from functools import wraps
from typing import Any, Dict, Optional, Tuple, Union

from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField
from wtforms.validators import DataRequired, Length, EqualTo
from sqlalchemy import inspect
import flask_migrate

# Configure logging before importing models
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(process)d - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    force=True
)
logger = logging.getLogger(__name__)

# Set third-party loggers to warning level to reduce noise
for logger_name in ['werkzeug', 'sqlalchemy', 'apscheduler']:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

logger.info("Starting application")
logger.info(f"Log level: {log_level}")

from models import db, User, Task, Settings, Block, BlockConnection
from database import session_scope, get_session
from executor import executor
from services.block_services import BlockValidationService, BlockProcessor
from scheduler import scheduler  # Import scheduler before using it

# Initialize Flask app
app = Flask(__name__)

# Configure app
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', f'sqlite:///{os.path.join(os.path.abspath(os.path.dirname(__file__)), "instance", "database.db")}')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db.init_app(app)
migrate = Migrate(app, db)

def initialize_database(app):
    """Initialize database, create tables, and handle migrations"""
    try:
        # Create database directory if it doesn't exist and ensure proper permissions
        instance_path = os.path.dirname(app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', ''))
        os.makedirs(instance_path, exist_ok=True)
        os.chmod(instance_path, 0o777)  # Ensure directory is writable
        
        # Touch the database file to ensure it exists and has proper permissions
        db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        if not os.path.exists(db_path):
            with open(db_path, 'a'):
                pass
            os.chmod(db_path, 0o666)  # Make database file writable
        
        with app.app_context():
            # Check if migrations directory exists and is properly initialized
            migrations_initialized = (
                os.path.exists('migrations/env.py') and
                os.path.exists('migrations/script.py.mako') and
                os.path.exists('migrations/alembic.ini')
            )
            
            if not migrations_initialized:
                logger.info("Migrations not properly initialized")
                try:
                    # Initialize migrations if they don't exist
                    if not os.path.exists('migrations'):
                        logger.info("Creating migrations directory")
                        os.makedirs('migrations', exist_ok=True)
                        os.chmod('migrations', 0o777)
                    
                    # Initialize migrations
                    logger.info("Initializing migrations")
                    flask_migrate.init()
                except Exception as e:
                    logger.error(f"Error initializing migrations: {str(e)}")
                    # If migrations fail, fall back to create_all
                    db.create_all()
                    return
            
            # Check for schema changes
            inspector = inspect(db.engine)
            current_metadata = db.Model.metadata
            current_metadata.reflect(bind=db.engine)
            
            expected_tables = set(current_metadata.tables.keys())
            existing_tables = set(inspector.get_table_names())
            
            needs_migration = False
            
            # Check for missing tables
            if missing_tables := expected_tables - existing_tables:
                logger.info(f"Missing tables detected: {missing_tables}")
                needs_migration = True
            
            # Check for schema changes in existing tables
            for table in existing_tables & expected_tables:
                expected_columns = {c.name for c in current_metadata.tables[table].columns}
                existing_columns = {c['name'] for c in inspector.get_columns(table)}
                
                if expected_columns != existing_columns:
                    logger.info(f"Schema mismatch in table {table}")
                    logger.debug(f"Expected columns: {expected_columns}")
                    logger.debug(f"Existing columns: {existing_columns}")
                    needs_migration = True
                    break
            
            if needs_migration:
                logger.info("Generating and applying database migrations")
                try:
                    flask_migrate.migrate()
                    flask_migrate.upgrade()
                    logger.info("Database migrations applied successfully")
                except Exception as e:
                    logger.error(f"Error applying migrations: {str(e)}", exc_info=True)
                    # If migrations fail, fall back to create_all
                    db.create_all()
            else:
                logger.info("No schema changes detected")
    
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}", exc_info=True)
        raise

# Initialize database with migrations
initialize_database(app)

# Initialize scheduler - but don't start it in Gunicorn workers
scheduler.init_app(app)

# Initialize secret key using session_scope
with session_scope() as session:
    secret_key = Settings.get_setting('SECRET_KEY', session=session)
    if not secret_key:
        secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
        Settings.set_setting('SECRET_KEY', secret_key, session=session)

app.config['SECRET_KEY'] = secret_key

from blocks.manager import manager

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
csrf = CSRFProtect(app)  # Initialize CSRF protection

# Common response helpers
def api_response(
    message: str,
    status: str = 'success',
    code: int = 200,
    **kwargs: Any
) -> Tuple[Dict[str, Any], int]:
    """Standardized API response helper
    
    Args:
        message: Response message
        status: Response status ('success' or 'error')
        code: HTTP status code
        **kwargs: Additional key-value pairs to include in response
        
    Returns:
        Tuple of (response dict, status code)
    """
    response = {
        'status': status,
        'message': message,
        **kwargs
    }
    return jsonify(response), code

def error_response(message: str, code: int = 400) -> Tuple[Dict[str, Any], int]:
    """Standardized error response helper
    
    Args:
        message: Error message
        code: HTTP status code
        
    Returns:
        Tuple of (error response dict, status code)
    """
    return api_response(message, status='error', code=code)

def task_access_required(f):
    """Decorator to check if user has access to task
    
    Checks if the task exists and belongs to the current user.
    Task ID should be the first argument after self/cls.
    """
    @wraps(f)
    def decorated_function(task_id: int, *args: Any, **kwargs: Any) -> Any:
        with session_scope() as session:
            task = session.get(Task, task_id)
            if not task:
                return error_response('Task not found', 404)
            if task.user_id != current_user.id:
                if request.is_json:
                    return error_response('Access denied', 403)
                flash('Access denied.', 'danger')
                return redirect(url_for('tasks'))
            return f(task, *args, **kwargs)
    return decorated_function

def with_transaction(f):
    """Decorator to handle database transactions
    
    Provides a session object as first argument to the decorated function.
    Handles commit/rollback automatically.
    """
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        with session_scope() as session:
            try:
                result = f(session, *args, **kwargs)
                return result
            except Exception as e:
                logger.error(f"Transaction error: {str(e)}", exc_info=True)
                raise
    return decorated_function

@app.teardown_appcontext
def remove_session(exception=None):
    """Remove the session at the end of the request"""
    session = get_session()
    session.remove()

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            if request.is_json:
                return jsonify({'error': 'Access denied. Admin privileges required.'}), 403
            flash('Access denied. Admin privileges required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def convert_parameter_value(value: str, param_type: str):
    """Convert parameter value to the correct type"""
    if param_type == 'integer':
        return int(value)
    elif param_type == 'float':
        return float(value)
    elif param_type == 'boolean':
        return value.lower() == 'true'
    return value

def validate_block_parameters(block_name: str, block_type: str, parameters: dict) -> dict:
    """Validate and convert block parameters
    
    Args:
        block_name: Name of the block
        block_type: Type of block (input, processing, or action)
        parameters: Dictionary of parameter values
        
    Returns:
        Dictionary of validated and converted parameters
        
    Raises:
        ValueError: If required parameters are missing or invalid
    """
    block_class = manager.get_block(block_type, block_name)
    if not block_class:
        raise ValueError(f"{block_type.title()} block {block_name} not found")
    
    # Instantiate block to get parameters
    block = block_class()
    validated_params = {}
    block_params = block.parameters
    
    for name, config in block_params.items():
        if name in parameters:
            try:
                validated_params[name] = convert_parameter_value(parameters[name], config['type'])
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid value for parameter {name}: {str(e)}")
        elif config.get('required', False):
            raise ValueError(f"Required parameter {name} is missing")
        elif 'default' in config:
            validated_params[name] = config['default']
    
    return validated_params

@login_manager.user_loader
def load_user(user_id):
    """Load user with thread-local session management"""
    session = get_session()
    try:
        # Use modern SQLAlchemy 2.0 API
        return session.get(User, int(user_id))
    except:
        return None

# Ensure user is attached to session for each request
@app.before_request
def before_request():
    if current_user.is_authenticated:
        session = get_session()
        # Check if the object is attached to a session
        if not inspect(current_user).persistent:
            current_user.query = session.query(User)
            session.merge(current_user)

# Template filters
@app.template_filter('status_badge')
def status_badge(status):
    return {
        'pending': 'badge-pending',
        'running': 'badge-running',
        'completed': 'badge-completed',
        'failed': 'badge-failed'
    }.get(status.lower(), 'badge-secondary')

@app.template_filter('datetime')
def format_datetime(value):
    """Format a datetime object to a string."""
    if not value:
        return ''
    return value.strftime('%Y-%m-%d %H:%M:%S')

# Web Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = LoginForm()
    return render_template('login.html', form=form)

@app.route('/dashboard')
@login_required
def dashboard():
    with session_scope() as session:
        # Get task statistics
        total_tasks = session.query(Task).filter_by(user_id=current_user.id).count()
        completed_tasks = session.query(Task).filter_by(user_id=current_user.id, status='completed').count()
        pending_tasks = session.query(Task).filter_by(user_id=current_user.id, status='pending').count()
        failed_tasks = session.query(Task).filter_by(user_id=current_user.id, status='failed').count()
        
        # Get recent tasks
        recent_tasks = session.query(Task).filter_by(user_id=current_user.id).order_by(Task.created_at.desc()).limit(5).all()
        
        # Get block statistics
        input_blocks = len(manager.get_blocks_by_type("input"))
        processing_blocks = len(manager.get_blocks_by_type("processing"))
        action_blocks = len(manager.get_blocks_by_type("action"))
        
        return render_template('dashboard.html',
            stats={
                'total_tasks': total_tasks,
                'completed_tasks': completed_tasks,
                'pending_tasks': pending_tasks,
                'failed_tasks': failed_tasks,
                'input_blocks': input_blocks,
                'processing_blocks': processing_blocks,
                'action_blocks': action_blocks
            },
            recent_tasks=recent_tasks
        )

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = LoginForm()
    if request.method == 'POST' and form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        
        if user and user.check_password(form.password.data):
            login_user(user)
            flash('Logged in successfully.', 'success')
            return redirect(url_for('dashboard'))
        
        flash('Invalid username or password.', 'danger')
    
    return render_template('login.html', form=form)

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=20)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = RegistrationForm()  # Create form instance
    
    if request.method == 'POST' and form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash('Username already exists.', 'danger')
            return redirect(url_for('register'))
        
        user = User(
            username=form.username.data,
            is_admin=User.query.count() == 0
        )
        user.set_password(form.password.data)
        
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful. Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html', form=form)  # Pass form to template

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route('/users')
@login_required
@admin_required
def users():
    users = User.get_all_users()
    return render_template('users.html', users=users)

@app.route('/users/create', methods=['POST'])
@login_required
@admin_required
def create_user():
    try:
        data = request.get_json()
        username = data['username']
        password = data['password']
        is_admin = data.get('is_admin', False)
        
        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'Username already exists'}), 400
        
        user = User(username=username, is_admin=is_admin)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        return jsonify({'message': 'User created successfully'})
        
    except KeyError as e:
        return jsonify({'error': f'Missing required field: {str(e)}'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/users/<int:user_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        return jsonify({'error': 'Cannot edit your own user through this interface'}), 400
    
    try:
        data = request.get_json()
        username = data['username']
        is_admin = data.get('is_admin', False)
        
        # Check if username is taken by another user
        existing_user = User.query.filter_by(username=username).first()
        if existing_user and existing_user.id != user_id:
            return jsonify({'error': 'Username already exists'}), 400
        
        user.username = username
        user.is_admin = is_admin
        
        # Update password if provided
        if data.get('password'):
            user.set_password(data['password'])
        
        db.session.commit()
        return jsonify({'message': 'User updated successfully'})
        
    except KeyError as e:
        return jsonify({'error': f'Missing required field: {str(e)}'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/users/<int:user_id>/deactivate', methods=['POST'])
@login_required
@admin_required
def deactivate_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        return jsonify({'error': 'Cannot deactivate your own account'}), 400
    
    user.deactivate()
    return jsonify({'status': 'success'})

@app.route('/users/<int:user_id>/activate', methods=['POST'])
@login_required
@admin_required
def activate_user(user_id):
    user = User.query.get_or_404(user_id)
    user.activate()
    return api_response('User activated successfully')

@app.route('/api/users/<int:user_id>')
@login_required
@admin_required
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    return api_response('User details retrieved successfully', user=user.to_dict())

class ProfileForm(FlaskForm):
    current_password = PasswordField('Current Password')
    new_password = PasswordField('New Password', validators=[Length(min=8)])
    confirm_password = PasswordField('Confirm Password', validators=[EqualTo('new_password')])

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = ProfileForm()
    if request.method == 'POST' and form.validate_on_submit():
        try:
            # Update password
            if form.new_password.data:
                if not current_user.check_password(form.current_password.data):
                    flash('Current password is incorrect.', 'danger')
                else:
                    current_user.set_password(form.new_password.data)
                    flash('Password updated successfully.', 'success')
            
            db.session.commit()
            flash('Profile updated successfully.', 'success')
            
        except Exception as e:
            flash(f'Error updating profile: {str(e)}', 'danger')
        
        return redirect(url_for('profile'))
    
    return render_template('profile.html', form=form)

@app.route('/tasks')
@login_required
def tasks():
    tasks = Task.query.filter_by(user_id=current_user.id).order_by(Task.created_at.desc()).all()
    return render_template('tasks.html', tasks=tasks)

@app.route('/tasks/new', methods=['GET', 'POST'])
@login_required
def new_task():
    if request.method == 'POST':
        try:
            logger.info("Creating new task")
            logger.debug(f"Form data: {request.form}")
            
            with session_scope() as session:
                # Create task
                task = Task(
                    name=request.form['name'],
                    user_id=current_user.id,
                    schedule=request.form.get('schedule')
                )
                session.add(task)
                session.flush()
                
                # Parse block data
                blocks_data = json.loads(request.form['blocks_data'])
                logger.debug(f"Blocks data: {blocks_data}")
                
                # Process blocks and connections
                blocks, block_errors = BlockProcessor.process_blocks(task, blocks_data, session)
                if block_errors:
                    return error_response('Invalid block configuration', details=block_errors)
                
                conn_errors = BlockProcessor.process_connections(blocks_data, blocks, session)
                if conn_errors:
                    return error_response('Invalid block connections', details=conn_errors)
                
                # Schedule the task if it has a schedule
                if task.schedule:
                    logger.info(f"Scheduling task with schedule: {task.schedule}")
                    scheduler.schedule_task(task)
                
                return api_response('Task created successfully', redirect=url_for('tasks'))
                
        except ValueError as e:
            logger.error(f"Error creating task: {str(e)}")
            return error_response(str(e))
        except Exception as e:
            logger.error(f"Unexpected error creating task: {str(e)}", exc_info=True)
            return error_response('An unexpected error occurred')
    
    # GET request - show form
    return render_template('task_form.html',
        task=None,
        input_blocks=manager.get_blocks_by_type('input'),
        processing_blocks=manager.get_blocks_by_type('processing'),
        action_blocks=manager.get_blocks_by_type('action')
    )

@app.route('/tasks/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
@task_access_required
def edit_task(task):
    if request.method == 'POST':
        try:
            logger.info(f"Editing task {task.id}")
            logger.debug(f"Form data: {request.form}")
            
            with session_scope() as session:
                task = session.merge(task)
                
                # Update basic task info
                task.name = request.form['name']
                task.schedule = request.form.get('schedule')
                
                # Parse block data
                blocks_data = json.loads(request.form['blocks_data'])
                logger.debug(f"Blocks data: {blocks_data}")
                
                # Create a map of existing blocks
                existing_blocks = {(block.name, block.type): block for block in task.blocks}
                
                # Process blocks and connections
                blocks, block_errors = BlockProcessor.process_blocks(
                    task, blocks_data, session, existing_blocks)
                if block_errors:
                    return error_response('Invalid block configuration', details=block_errors)
                
                conn_errors = BlockProcessor.process_connections(blocks_data, blocks, session)
                if conn_errors:
                    return error_response('Invalid block connections', details=conn_errors)
                
                # Update schedule
                if task.schedule:
                    logger.info(f"Updating schedule for task {task.id}: {task.schedule}")
                    scheduler.schedule_task(task)
                else:
                    logger.info(f"Removing schedule for task {task.id}")
                    scheduler.remove_task(task)
                
                return api_response('Task updated successfully', redirect=url_for('tasks'))
                
        except ValueError as e:
            logger.error(f"Error updating task {task.id}: {str(e)}")
            return error_response(str(e))
        except Exception as e:
            logger.error(f"Unexpected error updating task {task.id}: {str(e)}", exc_info=True)
            return error_response('An unexpected error occurred')
    
    # GET request - show form
    return render_template('task_form.html',
        task=task,
        blocks_data={
            'blocks': [{
                'id': block.id,
                'name': block.name,
                'type': block.type,
                'parameters': block.get_parameters(),
                'position_x': block.position_x,
                'position_y': block.position_y,
                'display_name': block.display_name or block.name
            } for block in task.blocks],
            'connections': [{
                'source': conn.source_block_id,
                'target': conn.target_block_id,
                'input_name': conn.input_name
            } for block in task.blocks for conn in block.inputs]
        },
        input_blocks=manager.get_blocks_by_type('input'),
        processing_blocks=manager.get_blocks_by_type('processing'),
        action_blocks=manager.get_blocks_by_type('action')
    )

@app.route('/tasks/<int:task_id>')
@login_required
def view_task(task_id):
    task = Task.query.get_or_404(task_id)
    if task.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('tasks'))
    
    # Organize parameters by block type
    parameters = {
        'input': {},
        'processing': {},
        'action': {}
    }
    
    for block in task.blocks:
        if block.type == 'input':
            parameters['input'] = block.get_parameters()
        elif block.type == 'processing':
            parameters['processing'][block.name] = block.get_parameters()
        elif block.type == 'action':
            parameters['action'] = block.get_parameters()
    
    return render_template('view_task.html',
        task=task,
        parameters=parameters,
        block_chain=task.get_block_chain(),
        block_data=task.get_block_data()
    )

@app.route('/api/tasks/<int:task_id>/run', methods=['POST'])
@login_required
@task_access_required
def run_task(task):
    try:
        with session_scope() as session:
            task = session.merge(task)
            task.update_status('running')
            
            # Run task in background thread
            thread = threading.Thread(target=run_in_thread, args=(app, task.id))
            thread.daemon = True
            thread.start()
            
            return api_response('Task started successfully')
            
    except Exception as e:
        logger.error(f"Error starting task {task.id}: {str(e)}", exc_info=True)
        task.update_status('failed')
        return error_response(str(e))

def run_in_thread(app, task_id):
    """Execute task in a separate thread with its own session"""
    with app.app_context():
        with session_scope() as session:
            try:
                task = session.get(Task, task_id)
                if not task:
                    logger.error(f"Task {task_id} not found")
                    return

                # Run the async function
                asyncio.run(executor.execute_task(task))
                
            except Exception as e:
                logger.error(f"Error executing task {task_id}: {str(e)}")
                task.update_status('failed')
                raise

@app.route('/api/blocks/<block_type>/<block_name>/parameters')
@login_required
def get_block_parameters(block_type, block_name):
    """Get parameters for a specific block
    
    Args:
        block_type: Type of block (input, processing, or action)
        block_name: Name of the block
        
    Returns:
        JSON object containing block parameters
    """
    block_class = manager.get_block(block_type, block_name)
    if not block_class:
        return error_response(f"{block_type.title()} block {block_name} not found", 404)
    
    block = block_class()
    return api_response('Block parameters retrieved successfully', parameters=block.parameters)

@app.route('/blocks')
@login_required
def blocks():
    """Display available blocks"""
    return render_template('blocks.html',
        input_blocks=manager.get_blocks_by_type('input'),
        processing_blocks=manager.get_blocks_by_type('processing'),
        action_blocks=manager.get_blocks_by_type('action')
    )

@app.route('/api/tasks/<int:task_id>/status')
@login_required
@task_access_required
def get_task_status(task):
    return api_response('Task status retrieved successfully',
        status=task.status,
        status_class=status_badge(task.status),
        last_run=format_datetime(task.last_run) if task.last_run else None,
        block_data=task.get_block_data()
    )

@app.route('/api/tasks/status')
@login_required
def get_tasks_status():
    # Get task IDs from query parameter
    task_ids = request.args.get('ids', '')
    if not task_ids:
        return error_response('No task IDs provided')
    
    try:
        # Convert comma-separated string to list of integers
        task_ids = [int(id) for id in task_ids.split(',')]
    except ValueError:
        return error_response('Invalid task ID format')
    
    # Query all tasks at once
    tasks = Task.query.filter(
        Task.id.in_(task_ids),
        Task.user_id == current_user.id
    ).all()
    
    # Build response dictionary
    response = {}
    for task in tasks:
        response[str(task.id)] = {
            'status': task.status,
            'status_class': status_badge(task.status),
            'last_run': format_datetime(task.last_run) if task.last_run else None,
            'block_data': task.get_block_data()
        }
    
    return api_response('Task statuses retrieved successfully', tasks=response)

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
@login_required
@task_access_required
def delete_task(task):
    try:
        with session_scope() as session:
            task = session.merge(task)
            
            # Remove task from scheduler if scheduled
            scheduler.remove_task(task)
            
            # Delete the task
            session.delete(task)
            
            return api_response('Task deleted successfully')
            
    except Exception as e:
        logger.error(f"Error deleting task {task.id}: {str(e)}", exc_info=True)
        return error_response('Failed to delete task')

@app.route('/api/tasks/<int:task_id>/blocks')
@login_required
@task_access_required
def get_task_blocks(task):
    """Get block data for a task"""
    blocks = [{
        'id': block.id,
        'name': block.name,
        'type': block.type,
        'parameters': block.get_parameters(),
        'position_x': block.position_x,
        'position_y': block.position_y,
        'display_name': block.display_name or block.name
    } for block in task.blocks]
    
    connections = [{
        'source': conn.source_block_id,
        'target': conn.target_block_id,
        'input_name': conn.input_name
    } for block in task.blocks for conn in block.inputs]
    
    return api_response('Block data retrieved successfully', 
                       blocks=blocks,
                       connections=connections)

if __name__ == '__main__':
    app.run(debug=True) 