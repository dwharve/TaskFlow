import asyncio
from datetime import datetime
import logging
from typing import Optional, Dict, Any
import threading
import traceback
import json
import queue
import time
import atexit
import os
import sys

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import and_
from flask import Flask, current_app

from models import Task, db, TaskLock
from blocks.manager import manager
from pubsub import pubsub, Message

logger = logging.getLogger(__name__)

# Topics for pub/sub communication
TASK_START_TOPIC = "task_start"
TASK_START_ACK_TOPIC = "task_start_ack"
TASK_COMPLETE_TOPIC = "task_complete"
TASK_FAILED_TOPIC = "task_failed"

class TaskScheduler:
    """Scheduler for running tasks on a schedule"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(TaskScheduler, cls).__new__(cls)
            return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            logger.info("Initializing TaskScheduler")
            self._running_tasks = {}
            self.scheduler = None
            self.app = None
            self._cleanup_lock = threading.Lock()
            self._task_queues: Dict[str, queue.Queue] = {}
            self._worker_id = f"worker_{int(time.time() * 1000)}"  # Unique ID for this worker
            self._setup_pubsub()
            self._initialized = True
            
            # Register cleanup on exit
            atexit.register(self.stop)
    
    def _setup_pubsub(self):
        """Setup pub/sub subscriptions"""
        # Subscribe to all task-related events
        self._task_queues[TASK_START_TOPIC] = pubsub.subscribe(TASK_START_TOPIC)
        self._task_queues[TASK_START_ACK_TOPIC] = pubsub.subscribe(TASK_START_ACK_TOPIC)
        self._task_queues[TASK_COMPLETE_TOPIC] = pubsub.subscribe(TASK_COMPLETE_TOPIC)
        self._task_queues[TASK_FAILED_TOPIC] = pubsub.subscribe(TASK_FAILED_TOPIC)
        
        # Start listener thread
        self._listener_thread = threading.Thread(target=self._listen_for_events, daemon=True)
        self._listener_thread.start()
    
    def _listen_for_events(self):
        """Listen for task events from other workers"""
        while True:
            try:
                # Check start requests
                try:
                    message = self._task_queues[TASK_START_TOPIC].get_nowait()
                    task_id = message.data
                    # If we're running this task, acknowledge it
                    if task_id in self._running_tasks:
                        logger.info(f"Task {task_id} is already running on this worker, sending ACK")
                        pubsub.publish(TASK_START_ACK_TOPIC, {
                            'task_id': task_id,
                            'worker_id': self._worker_id
                        })
                except queue.Empty:
                    pass
                
                # Check start acknowledgments
                try:
                    message = self._task_queues[TASK_START_ACK_TOPIC].get_nowait()
                    data = message.data
                    task_id = data['task_id']
                    worker_id = data['worker_id']
                    if worker_id != self._worker_id:
                        logger.info(f"Task {task_id} is already running on worker {worker_id}")
                        self._cleanup_task(task_id)
                except queue.Empty:
                    pass
                
                # Check complete queue
                try:
                    message = self._task_queues[TASK_COMPLETE_TOPIC].get_nowait()
                    data = message.data
                    task_id = data['task_id']
                    worker_id = data['worker_id']
                    logger.info(f"Received task completion notification for task {task_id} from worker {worker_id}")
                    if worker_id == self._worker_id:
                        self._cleanup_task(task_id)
                except queue.Empty:
                    pass
                
                # Check failed queue
                try:
                    message = self._task_queues[TASK_FAILED_TOPIC].get_nowait()
                    data = message.data
                    task_id = data['task_id']
                    worker_id = data['worker_id']
                    logger.info(f"Received task failure notification for task {task_id} from worker {worker_id}")
                    if worker_id == self._worker_id:
                        self._cleanup_task(task_id)
                except queue.Empty:
                    pass
                
                # Sleep briefly to prevent tight loop
                threading.Event().wait(0.1)
                
            except Exception as e:
                logger.error(f"Error in event listener: {str(e)}")
                logger.error(traceback.format_exc())
    
    def _cleanup_task(self, task_id: int):
        """Clean up after task completion
        
        Args:
            task_id: ID of completed task
        """
        with self._cleanup_lock:
            if task_id in self._running_tasks:
                thread = self._running_tasks.pop(task_id)
                logger.info(f"Cleaned up task {task_id}. Thread alive: {thread.is_alive()}")
    
    def init_app(self, app: Flask):
        """Initialize the scheduler with Flask app
        
        Args:
            app: Flask application instance
        """
        self.app = app
        
        # Detect if this is a worker process
        # In Gunicorn, worker processes will have 'gunicorn' in their parent process name
        is_worker = False
        try:
            import psutil
            current_process = psutil.Process()
            parent_process = current_process.parent()
            is_worker = parent_process and 'gunicorn' in parent_process.name().lower()
        except:
            # If psutil fails, fallback to checking if this is the main thread
            is_worker = threading.current_thread() is not threading.main_thread()
        
        if not is_worker:
            logger.info("Initializing scheduler in main process")
            self.scheduler = BackgroundScheduler()
        else:
            logger.info("Worker process detected - skipping scheduler initialization")
            self.scheduler = None
            
        logger.info("Initialized scheduler with Flask app")
    
    def _load_existing_tasks(self):
        """Load and schedule existing tasks from the database"""
        if not self.app:
            logger.error("Cannot load tasks: Flask app not initialized")
            return 0
            
        try:
            with self.app.app_context():
                # Query for all tasks that have a schedule
                tasks = Task.query.filter(
                    and_(
                        Task.schedule.isnot(None),
                        Task.schedule != ''
                    )
                ).all()
                
                logger.info(f"Found {len(tasks)} scheduled tasks in database")
                
                # Schedule each task
                for task in tasks:
                    try:
                        self.schedule_task(task)
                    except Exception as e:
                        logger.error(f"Failed to schedule existing task {task.id}: {str(e)}")
                        logger.error(f"Traceback: {traceback.format_exc()}")
                        continue
                
                return len(tasks)
        except Exception as e:
            logger.error(f"Error loading existing tasks: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return 0
    
    def start(self):
        """Start the scheduler"""
        if not self.app:
            logger.error("Cannot start scheduler: Flask app not initialized")
            raise RuntimeError("Flask app not initialized")
        
        # Only start scheduler in main process
        if self.scheduler is None:
            logger.info("Worker process - skipping scheduler start")
            return
            
        try:
            self.scheduler.start()
            logger.info("Scheduler started successfully")
            
            # Load and schedule existing tasks
            num_tasks = self._load_existing_tasks()
            
            # Log currently scheduled jobs
            jobs = self.scheduler.get_jobs()
            logger.info(f"Loaded {num_tasks} tasks from database")
            logger.info(f"Currently scheduled jobs: {len(jobs)}")
            for job in jobs:
                next_run = job.next_run_time.strftime('%Y-%m-%d %H:%M:%S') if job.next_run_time else 'None'
                logger.info(f"Job ID: {job.id}, Next run time: {next_run}")
                
        except Exception as e:
            logger.error(f"Failed to start scheduler: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise
    
    def stop(self):
        """Stop the scheduler"""
        logger.info("Stopping scheduler")
        try:
            self.scheduler.shutdown()
            logger.info("Scheduler shutdown complete")
            
            # Stop any running tasks
            running_tasks = list(self._running_tasks.items())
            logger.info(f"Stopping {len(running_tasks)} running tasks")
            for task_id, thread in running_tasks:
                logger.info(f"Waiting for task {task_id} to complete")
                self.cleanup_task_resources(task_id)
        except Exception as e:
            logger.error(f"Error during scheduler shutdown: {str(e)}")
            raise
    
    def schedule_task(self, task: Task):
        """Schedule a task to run
        
        Args:
            task: Task to schedule
        """
        logger.info(f"Scheduling task {task.id} with schedule: {task.schedule}")
        if not task.schedule:
            logger.info(f"Task {task.id} has no schedule, skipping")
            return
        
        try:
            # Remove any existing job
            try:
                self.scheduler.remove_job(str(task.id))
                logger.info(f"Successfully removed existing job for task {task.id}")
            except Exception as e:
                logger.debug(f"No existing job found for task {task.id}: {str(e)}")
            
            # Parse cron schedule for logging
            trigger = CronTrigger.from_crontab(task.schedule)
            next_run = trigger.get_next_fire_time(None, datetime.now())
            
            # Create new job
            self.scheduler.add_job(
                self.run_task,
                trigger,
                args=[task.id],
                id=str(task.id),
                replace_existing=True,
                misfire_grace_time=None  # Disable grace time to prevent misfired jobs from running
            )
            logger.info(f"Successfully scheduled task {task.id}. Next run at: {next_run}")
            
        except Exception as e:
            logger.error(f"Failed to schedule task {task.id}: {str(e)}")
            logger.debug(f"Schedule string: {task.schedule}")
            raise
    
    def remove_task(self, task: Task):
        """Remove a task from the scheduler
        
        Args:
            task: Task to remove
        """
        logger.info(f"Removing task {task.id} from scheduler")
        try:
            # Remove the job
            self.scheduler.remove_job(str(task.id))
            logger.info(f"Successfully removed task {task.id} from scheduler")
            
            # Also remove from running tasks if it's there
            if task.id in self._running_tasks:
                thread = self._running_tasks.pop(task.id)
                logger.info(f"Removed task {task.id} from running tasks. Thread alive: {thread.is_alive()}")
                
        except Exception as e:
            logger.debug(f"Error removing task {task.id} (may not have been scheduled): {str(e)}")
    
    def run_task(self, task_id: int):
        """Run a task
        
        Args:
            task_id: ID of the task to run
        """
        if not self.app:
            logger.error(f"Cannot run task {task_id}: Flask app not initialized")
            return
            
        logger.info(f"Initiating task run for task {task_id}")
        
        # Check if task is already running locally
        with self._cleanup_lock:
            if task_id in self._running_tasks:
                logger.info(f"Task {task_id} is already running locally")
                return
        
        # Try to acquire task lock
        if not TaskLock.acquire_lock(task_id, self._worker_id):
            logger.info(f"Could not acquire lock for task {task_id}, another worker is likely running it")
            return
            
        try:
            with self._cleanup_lock:
                if task_id not in self._running_tasks:
                    logger.info(f"Starting task {task_id}")
                    thread = threading.Thread(
                        target=self._run_task_thread,
                        args=(task_id,),
                        name=f"Task-{task_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                    )
                    thread.daemon = True
                    self._running_tasks[task_id] = thread
                    thread.start()
                    logger.info(f"Started thread {thread.name} for task {task_id}")
                else:
                    logger.info(f"Task {task_id} is already running locally")
        except Exception as e:
            logger.error(f"Error starting task {task_id}: {str(e)}")
            # Make sure to release lock if we fail to start the task
            TaskLock.release_lock(task_id, self._worker_id)
            raise
    
    def cleanup_task_resources(self, task_id):
        """Clean up all resources associated with a task"""
        with self._cleanup_lock:
            if task_id in self._running_tasks:
                thread = self._running_tasks.pop(task_id)
                try:
                    # Only try to join if it's not the current thread
                    if thread.ident != threading.current_thread().ident:
                        if thread.is_alive():
                            thread.join(timeout=1)
                except Exception as e:
                    logger.error(f"Error while joining task thread {task_id}: {str(e)}")
                finally:
                    # Always remove from running tasks and release lock
                    TaskLock.release_lock(task_id, self._worker_id)
                    logger.info(f"Cleaned up resources for task {task_id}")
    
    def _run_task_thread(self, task_id: int):
        """Run a task in a separate thread
        
        Args:
            task_id: ID of the task to run
        """
        try:
            with self.app.app_context():
                task = Task.query.get(task_id)
                if not task:
                    logger.error(f"Task {task_id} not found")
                    return
                
                logger.info(f"Starting execution of task {task_id} - {task.name}")
                task.update_status('running')
                
                # Execute the task
                asyncio.run(self._execute_task(task))
                
                # Update task status
                task.update_status('completed')
                
        except Exception as e:
            logger.error(f"Error executing task {task_id}: {str(e)}")
            logger.error(traceback.format_exc())
            with self.app.app_context():
                task = Task.query.get(task_id)
                if task:
                    task.update_status('failed')
            
        finally:
            # Always release lock when task is done
            TaskLock.release_lock(task_id, self._worker_id)
            # Use a separate thread for cleanup to avoid self-join
            cleanup_thread = threading.Thread(
                target=self.cleanup_task_resources,
                args=(task_id,),
                daemon=True
            )
            cleanup_thread.start()
    
    async def _execute_task(self, task: Task):
        """Execute a task
        
        Args:
            task: Task to execute
        """
        logger.info(f"Beginning block chain execution for task {task.id}")
        try:
            # Log block chain information
            blocks = task.blocks
            logger.info(f"Task {task.id} has {len(blocks)} blocks to execute")
            for block in blocks:
                logger.info(f"Block: {block.name} (Type: {block.type})")
            
            # Execute block chain
            logger.info(f"Executing block chain for task {task.id}")
            results = await manager.execute_block_chain(task)
            
            # Store results
            logger.info(f"Storing results for task {task.id}")
            task.set_block_data(results)
            db.session.commit()
            logger.info(f"Successfully stored results for task {task.id}")
            
        except Exception as e:
            logger.error(f"Error executing block chain for task {task.id}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

# Global instance
scheduler = TaskScheduler() 