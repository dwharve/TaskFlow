import asyncio
from datetime import datetime
import logging
from typing import Optional, Dict, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from models import Task, db
from blocks.manager import manager

logger = logging.getLogger(__name__)

class TaskScheduler:
    """Scheduler for running tasks on a schedule"""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._running_tasks: Dict[int, asyncio.Task] = {}
    
    def start(self):
        """Start the scheduler"""
        self.scheduler.start()
        logger.info("Scheduler started")
    
    def stop(self):
        """Stop the scheduler"""
        self.scheduler.shutdown()
        logger.info("Scheduler stopped")
        
        # Cancel any running tasks
        for task in self._running_tasks.values():
            task.cancel()
    
    def schedule_task(self, task: Task):
        """Schedule a task to run
        
        Args:
            task: Task to schedule
        """
        if not task.schedule:
            return
        
        # Remove any existing job
        self.remove_task(task)
        
        # Create new job
        self.scheduler.add_job(
            self.run_task,
            CronTrigger.from_crontab(task.schedule),
            args=[task.id],
            id=str(task.id),
            replace_existing=True
        )
        logger.info(f"Scheduled task {task.id} with schedule {task.schedule}")
    
    def remove_task(self, task: Task):
        """Remove a task from the scheduler
        
        Args:
            task: Task to remove
        """
        try:
            self.scheduler.remove_job(str(task.id))
            logger.info(f"Removed task {task.id} from scheduler")
        except:
            pass
    
    async def run_task(self, task_id: int):
        """Run a task
        
        Args:
            task_id: ID of the task to run
        """
        # Check if task is already running
        if task_id in self._running_tasks:
            logger.warning(f"Task {task_id} is already running")
            return
        
        # Get task
        task = Task.query.get(task_id)
        if not task:
            logger.error(f"Task {task_id} not found")
            return
        
        # Update task status
        task.status = 'running'
        task.last_run = datetime.utcnow()
        db.session.commit()
        
        try:
            # Create asyncio task
            self._running_tasks[task_id] = asyncio.create_task(
                self._execute_task(task)
            )
            
            # Wait for task to complete
            await self._running_tasks[task_id]
            
            # Update task status
            task.status = 'completed'
            db.session.commit()
            
        except Exception as e:
            logger.error(f"Error running task {task_id}: {str(e)}")
            task.status = 'failed'
            db.session.commit()
        
        finally:
            # Remove task from running tasks
            self._running_tasks.pop(task_id, None)
    
    async def _execute_task(self, task: Task):
        """Execute a task
        
        Args:
            task: Task to execute
        """
        try:
            # Execute block chain
            results = await manager.execute_block_chain(task)
            
            # Store results
            task.set_block_data(results)
            db.session.commit()
            
        except Exception as e:
            logger.error(f"Error executing task {task.id}: {str(e)}")
            raise

# Global instance
scheduler = TaskScheduler() 