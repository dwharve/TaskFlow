import sys
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from functools import wraps
import os
from datetime import datetime
import json
import asyncio
import logging
import secrets
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField
from wtforms.validators import DataRequired, Length, EqualTo
import threading
from sqlalchemy import inspect
import flask_migrate

from models import db, User, Task, Settings, Block, BlockConnection
from database import session_scope, get_session
from executor import executor

# Initialize Flask app
app = Flask(__name__)

# Get log level from environment
log_level = os.environ.get('LOG_LEVEL', 'INFO')
# Get log level from arguments
# log_level = sys.argv[1] if len(sys.argv) > 1 else log_level

# Set up logging with pid and thread name
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(process)d - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    force=True  # Force reconfiguration of the root logger
)
logger = logging.getLogger(__name__)
logger.info("Starting application")
logger.info(f"Log level: {log_level}")

# Set third-party loggers to warning level to reduce noise
logging.getLogger('werkzeug').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
logging.getLogger('apscheduler').setLevel(logging.WARNING)

@app.teardown_appcontext
def remove_session(exception=None):
    """Remove the session at the end of the request"""
    session = get_session()
    session.remove()

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['WTF_CSRF_ENABLED'] = True

# Initialize extensions
db.init_app(app)
migrate = Migrate(app, db)

with app.app_context():
    try:
        # Create database directory if it doesn't exist
        os.makedirs('instance', exist_ok=True)
        
        # Initialize migrations directory if it doesn't exist
        if not os.path.exists('migrations'):
            logger.info("Initializing migrations directory")
            migrate.init_app(app, db)
            with app.app_context():
                flask_migrate.init()
        
        # Create database if it doesn't exist
        if not os.path.exists('instance/database.db'):
            db.create_all()
            logger.info("Created new database")
        
        # Check if any tables are missing and create them
        inspector = inspect(db.engine)
        current_metadata = db.Model.metadata
        current_metadata.reflect(bind=db.engine)
        
        # Get the list of tables from the models and database
        expected_tables = set(current_metadata.tables.keys())
        existing_tables = set(inspector.get_table_names())
        
        # Check for missing tables or schema changes
        needs_migration = False
        
        # Check for missing tables
        if expected_tables - existing_tables:
            logger.info(f"Missing tables detected: {expected_tables - existing_tables}")
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
                # Generate migration
                with app.app_context():
                    flask_migrate.migrate()
                    # Apply migration
                    flask_migrate.upgrade()
                logger.info("Database migrations applied successfully")
            except Exception as e:
                logger.error(f"Error applying migrations: {str(e)}", exc_info=True)
                raise
    
    except Exception as e:
        logger.error(f"Error checking/creating tables: {str(e)}", exc_info=True)
        raise

# Check if secret key is in database
secret_key = Settings.get_setting('SECRET_KEY')
if not secret_key:
    secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
    Settings.set_setting('SECRET_KEY', secret_key)

app.config['SECRET_KEY'] = secret_key

# Initialize and start scheduler
from scheduler import scheduler
scheduler.init_app(app)
scheduler.start()

from blocks.manager import manager

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
csrf = CSRFProtect(app)  # Initialize CSRF protection

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
    return jsonify({'status': 'success'})

@app.route('/api/users/<int:user_id>')
@login_required
@admin_required
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict())

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
            
            # Create task
            with session_scope() as session:
                task = Task(
                    name=request.form['name'],
                    user_id=current_user.id,
                    schedule=request.form.get('schedule')
                )
                session.add(task)
                session.flush()  # Get task ID
                
                # Parse block data
                blocks_data = json.loads(request.form['blocks_data'])
                logger.debug(f"Blocks data: {blocks_data}")
                
                # Create blocks
                blocks = {}  # id -> Block
                for block_data in blocks_data['blocks']:
                    block = Block(
                        task_id=task.id,
                        name=block_data['name'],
                        type=block_data['type'],
                        display_name=block_data.get('display_name'),
                        position_x=block_data.get('position_x', 0),
                        position_y=block_data.get('position_y', 0)
                    )
                    
                    # Get parameters for this block
                    block_params = {}
                    param_prefix = f'{block.type}_param_{block.name}_'
                    for key, value in request.form.items():
                        if key.startswith(param_prefix):
                            param_name = key.replace(param_prefix, '')
                            block_params[param_name] = value
                    
                    # Use block parameters directly from blocks_data
                    if 'parameters' in block_data:
                        block_params = block_data['parameters']
                    
                    # Validate parameters
                    block_params = validate_block_parameters(
                        block.name, block.type, block_params)
                    block.set_parameters(block_params)
                    
                    session.add(block)
                    session.flush()  # Get block ID
                    blocks[block_data['id']] = block
                
                # Create connections
                blocks_list = list(blocks.values())  # Convert blocks dict to list for indexing
                for conn_data in blocks_data['connections']:
                    source_index = int(conn_data['source'])
                    target_index = int(conn_data['target'])
                    
                    if 0 <= source_index < len(blocks_list) and 0 <= target_index < len(blocks_list):
                        conn = BlockConnection(
                            source_block_id=blocks_list[source_index].id,
                            target_block_id=blocks_list[target_index].id,
                            input_name=conn_data.get('input_name')
                        )
                        session.add(conn)
                    else:
                        logger.error(f"Invalid connection indices: source={source_index}, target={target_index}, blocks_len={len(blocks_list)}")
                
                # Schedule the task if it has a schedule
                if task.schedule:
                    logger.info(f"Scheduling task with schedule: {task.schedule}")
                    scheduler.schedule_task(task)
            
            # Return JSON response for AJAX request
            return jsonify({
                'status': 'success',
                'message': 'Task created successfully',
                'redirect': url_for('tasks')
            })
            
        except ValueError as e:
            logger.error(f"Error creating task: {str(e)}")
            return jsonify({
                'status': 'error',
                'error': str(e)
            }), 400
        except Exception as e:
            logger.error(f"Unexpected error creating task: {str(e)}", exc_info=True)
            return jsonify({
                'status': 'error',
                'error': 'An unexpected error occurred.'
            }), 500
    
    # GET request - show form
    return render_template('task_form.html',
        task=None,
        input_blocks=manager.get_blocks_by_type('input'),
        processing_blocks=manager.get_blocks_by_type('processing'),
        action_blocks=manager.get_blocks_by_type('action')
    )

@app.route('/tasks/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    task = Task.query.get_or_404(task_id)
    if task.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('tasks'))
    
    if request.method == 'POST':
        try:
            logger.info(f"Editing task {task_id}")
            logger.debug(f"Form data: {request.form}")
            
            with session_scope() as session:
                task = session.get(Task, task_id)
                
                # Update basic task info
                task.name = request.form['name']
                task.schedule = request.form.get('schedule')
                
                # Parse block data
                blocks_data = json.loads(request.form['blocks_data'])
                logger.debug(f"Blocks data: {blocks_data}")
                
                # Create a map of existing blocks by name and type
                existing_blocks = {(block.name, block.type): block for block in task.blocks}
                
                # Track which blocks are still in use
                used_blocks = set()
                
                # Update or create blocks
                blocks = {}
                for block_data in blocks_data['blocks']:
                    block_key = (block_data['name'], block_data['type'])
                    
                    if block_key in existing_blocks:
                        # Update existing block
                        block = existing_blocks[block_key]
                        block.display_name = block_data.get('display_name')
                        block.position_x = block_data.get('position_x', 0)
                        block.position_y = block_data.get('position_y', 0)
                        used_blocks.add(block_key)
                    else:
                        # Create new block
                        block = Block(
                            task_id=task.id,
                            name=block_data['name'],
                            type=block_data['type'],
                            display_name=block_data.get('display_name'),
                            position_x=block_data.get('position_x', 0),
                            position_y=block_data.get('position_y', 0)
                        )
                        session.add(block)
                    
                    # Update parameters
                    if 'parameters' in block_data:
                        block_params = block_data['parameters']
                        # Validate parameters
                        block_params = validate_block_parameters(
                            block.name, block.type, block_params)
                        block.set_parameters(block_params)
                    
                    session.flush()  # Get block ID
                    blocks[block_data['id']] = block
                
                # Remove blocks that are no longer used
                for block_key, block in existing_blocks.items():
                    if block_key not in used_blocks:
                        session.delete(block)
                
                # Delete all existing connections
                for block in task.blocks:
                    for conn in block.inputs:
                        session.delete(conn)
                
                # Create new connections
                blocks_list = list(blocks.values())  # Convert blocks dict to list for indexing
                for conn_data in blocks_data['connections']:
                    source_index = int(conn_data['source'])
                    target_index = int(conn_data['target'])
                    
                    if 0 <= source_index < len(blocks_list) and 0 <= target_index < len(blocks_list):
                        conn = BlockConnection(
                            source_block_id=blocks_list[source_index].id,
                            target_block_id=blocks_list[target_index].id,
                            input_name=conn_data.get('input_name')
                        )
                        session.add(conn)
                    else:
                        logger.error(f"Invalid connection indices: source={source_index}, target={target_index}, blocks_len={len(blocks_list)}")
                
                # Update schedule
                if task.schedule:
                    logger.info(f"Updating schedule for task {task_id}: {task.schedule}")
                    scheduler.schedule_task(task)
                else:
                    logger.info(f"Removing schedule for task {task_id}")
                    scheduler.remove_task(task)
            
            # Return JSON response for AJAX request
            return jsonify({
                'status': 'success',
                'message': 'Task updated successfully',
                'redirect': url_for('tasks')
            })
            
        except ValueError as e:
            logger.error(f"Error updating task {task_id}: {str(e)}")
            return jsonify({
                'status': 'error',
                'error': str(e)
            }), 400
        except Exception as e:
            logger.error(f"Unexpected error updating task {task_id}: {str(e)}", exc_info=True)
            return jsonify({
                'status': 'error',
                'error': 'An unexpected error occurred.'
            }), 500
    
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
def run_task(task_id):
    with session_scope() as session:
        task = session.get(Task, task_id)
        if not task:
            return jsonify({'error': 'Task not found'}), 404
        
        if task.user_id != current_user.id and not current_user.is_admin:
            return jsonify({'error': 'Unauthorized'}), 403
        
        try:
            task.update_status('running')
            session.commit()
            
            # Run task in background thread
            thread = threading.Thread(target=run_in_thread, args=(app, task_id))
            thread.daemon = True
            thread.start()
            
            return jsonify({'message': 'Task started successfully'})
        except Exception as e:
            logger.error(f"Error starting task {task_id}: {str(e)}")
            task.update_status('failed')
            return jsonify({'error': str(e)}), 500

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
        return jsonify({'error': f"{block_type.title()} block {block_name} not found"}), 404
    
    block = block_class()
    return jsonify(block.parameters)

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
def get_task_status(task_id):
    task = Task.query.get_or_404(task_id)
    if task.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403
    
    return jsonify({
        'status': task.status,
        'status_class': status_badge(task.status),
        'last_run': format_datetime(task.last_run) if task.last_run else None,
        'block_data': task.get_block_data()
    })

@app.route('/api/tasks/status')
@login_required
def get_tasks_status():
    # Get task IDs from query parameter
    task_ids = request.args.get('ids', '')
    if not task_ids:
        return jsonify({'error': 'No task IDs provided'}), 400
    
    try:
        # Convert comma-separated string to list of integers
        task_ids = [int(id) for id in task_ids.split(',')]
    except ValueError:
        return jsonify({'error': 'Invalid task ID format'}), 400
    
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
    
    return jsonify(response)

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
@login_required
def delete_task(task_id):
    with session_scope() as session:
        task = session.get(Task, task_id)
        if not task:
            return jsonify({'error': 'Task not found'}), 404
        
        if task.user_id != current_user.id:
            return jsonify({'error': 'Access denied'}), 403
        
        try:
            # Remove task from scheduler if scheduled
            scheduler.remove_task(task)
            
            # Delete the task
            session.delete(task)
            
            return jsonify({'message': 'Task deleted successfully'})
        except Exception as e:
            logger.error(f"Error deleting task {task_id}: {str(e)}")
            return jsonify({'error': 'Failed to delete task'}), 500

@app.route('/api/tasks/<int:task_id>/blocks')
@login_required
def get_task_blocks(task_id):
    """Get block data for a task"""
    task = Task.query.get_or_404(task_id)
    if task.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403
    
    blocks_data = {
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
    }
    
    return jsonify(blocks_data)

if __name__ == '__main__':
    app.run(debug=True) 