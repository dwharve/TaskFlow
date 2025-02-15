import os
import sys
from app import app
from scheduler import scheduler
import multiprocessing
import logging

logger = logging.getLogger(__name__)
scheduler_process = None

def run_scheduler():
    """Run the scheduler in a separate process"""
    try:
        with app.app_context():
            scheduler.init_app(app)
            scheduler.start()
            # Keep the process running
            while True:
                multiprocessing.Event().wait()
    except Exception as e:
        logger.error(f"Scheduler process error: {str(e)}")
        sys.exit(1)

def on_starting(server):
    """Gunicorn hook for when the master process is starting"""
    global scheduler_process
    logger.info("Starting scheduler process from master")
    scheduler_process = multiprocessing.Process(
        target=run_scheduler,
        name='TaskScheduler'
    )
    scheduler_process.daemon = True
    scheduler_process.start()
    logger.info(f"Started scheduler process (PID: {scheduler_process.pid})")

def on_exit(server):
    """Gunicorn hook for when the master process is exiting"""
    global scheduler_process
    if scheduler_process:
        logger.info("Stopping scheduler process")
        scheduler_process.terminate()
        scheduler_process.join(timeout=5)
        if scheduler_process.is_alive():
            logger.warning("Scheduler process did not terminate gracefully, forcing...")
            scheduler_process.kill()

# For development/testing without gunicorn
if __name__ == '__main__':
    with app.app_context():
        scheduler.init_app(app)
        scheduler.start()
        app.run() 